# 抖音视频 → 逐字稿（转写链路）

本文件是 SKILL.md 步骤 1–2（取流 + 转写）的详细实现。用户发来抖音分享链接要「逐字稿」时，用这条链路把口播转成文字。**不需要用户提供任何额外东西**，全程约 2–4 分钟（首次要下模型）。

## 不要走的路（已验证失败）

| 方案 | 结果 |
|---|---|
| `yt-dlp <抖音链接>` | ❌ `Fresh cookies (not necessarily logged in) are needed` |
| curl 抓分享页 HTML | ❌ JS 渲染，拿不到内容 |
| 页面 `<video>` 标签的 src | ❌ 是 `blob:` MSE 流，无法下载 |
| 分享页 `_ROUTER_DATA` 里找 `playAddr` | ❌ **2026-11-02 实测已失效**：只剩 ua/query/renderInSSR 等路由元数据（1399 字节），无播放地址 |
| `iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids=<id>` | ❌ 返回 **0 字节**（接口已废弃） |
| `douyin.com/aweme/v1/web/aweme/detail/?aweme_id=<id>` | ❌ `Blocked by ArgusSecurityPlugin Uifid Not Found`，桌面 web API 全走签名 |

> **结论（2026-11-02）**：抖音的分享页与开放接口都已封死，**只能在真实浏览器里执行 JS 取流**。
> `agent-browser` 命令在多数机器上并不存在，请用 `scripts/grab_stream.py`（Playwright 驱动系统 Chrome）。

## 正确链路

### 1. 拿到视频 ID

```bash
curl -s -o /dev/null -w "%{url_effective}\n" -L -m 20 \
  -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  "https://v.douyin.com/XXXXXX/"
# → https://www.iesdouyin.com/share/video/<VIDEO_ID>/?...
```

### 2. 抓流地址 + 作者信息（浏览器内 JS）

**首选：`scripts/grab_stream.py`**（Playwright 驱动系统已装的 Chrome，不需要下载浏览器内核）

```bash
python3 scripts/grab_stream.py <VIDEO_ID>
# 输出 {video_id, url, method, meta, video_duration}
```

- `meta` 里含「`<标题>` - `<作者昵称>`于`YYYYMMDD`发布在抖音，已经收获了`N`个喜欢」
  → **用它判断这是不是用户自己的号**（涉及版权，是别人视频不要直接搬）
- `video_duration` 是秒数，可用来判断篇幅（70 秒 ≈ 330 字口语）

前置：`pip install playwright` + 系统装有 Google Chrome（脚本用 `channel="chrome"`）。
若报 `Executable doesn't exist`，说明 playwright 内核没装，**不要**去 `playwright install`，
用 `channel="chrome"` 即可（脚本默认如此）。

> ⚠️ **必须 headed**（不要加 `--headless`）：抖音对 headless 更敏感。
> 脚本已带 `--autoplay-policy=no-user-gesture-required` + 静音播放，这是让媒体资源进 `performance` 的前提。

### 2b. 三条取流路径（并列，谁先命中用谁）

**2026-11-02 实测：`performance` 未命中纯音频流，但 `video.currentSrc` 直接拿到完整视频流（br=1308）。**
所以**不要把 performance 当唯一首选**，两条并列试：

| 路径 | 拿到什么 | 说明 |
|---|---|---|
| `performance` 过滤 `media-audio-und-mp4a` | **纯音频** | 最优：265 秒视频只 2.1 MB，下载转码都快一大截。同一次播放里的 `media-video-avc1` 是视频，**别选它** |
| `video.currentSrc` | **完整视频流** | 形如 `.../video/tos/cn/.../?a=6383&br=1308&...`。2026-11-02 实测这条直接可用 |
| 页面 HTML 正则搜 `douyinvod` | 直链 | 前两条都失效时的兜底。注意 `&` 被转义成 `&amp;`，要还原 |

拿到的是 `blob:` 说明走 MSE，三条都失效 → 换 headed 重试，或让用户手动提供视频文件。

### 2c. 取 URL 的引号坑（不处理必 404）

脚本输出的是 JSON，取 `url` 字段时记得剥掉引号：

```bash
PY=python3
URL=$($PY -c "import json;print(json.load(open('stream_result.json'))['url'])")
```

### 3. 立刻下载（URL 有签名时效）

```bash
curl -s -L -m 180 -o video.mp4 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -e "https://www.douyin.com/" "<上一步的 URL>"
```

**必须带 Referer**，否则 403。

### 4. 转码

```bash
ffmpeg -y -loglevel error -i video.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le audio.wav
```

### 5. 转写（faster-whisper）

首次安装：

```bash
python3 -m venv "$HOME/.venvs/whisper" && "$HOME/.venvs/whisper/bin/pip" install -q -U faster-whisper
```

跑：

```bash
HF_ENDPOINT=https://hf-mirror.com "$HOME/.venvs/whisper/bin/python" - <<'PY'
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe(
    "audio.wav", language="zh", beam_size=5,
    vad_filter=False,                        # ← 必须 False，见下方坑
    initial_prompt="以下是普通话口播视频的逐字稿。",
)
out = []
for s in segments:
    out.append(s.text.strip())
print("".join(out))
PY
```

## 两个必须记住的坑

### 1. `vad_filter=True` 会直接崩

报错：`ImportError: ... onnxruntime_pybind11_state.so ... built for macOS 13.4 which is newer than running OS`。
`onnxruntime`（VAD 依赖）编译目标比本机 macOS 新，装不上也修不了。**`vad_filter=False` 即可绕过**——VAD 只影响静音切分，转写主体不依赖它。代价：静音段可能产生少量幻觉文本，看一遍删掉即可。

### 2. 模型下载要挂镜像

`HF_ENDPOINT=https://hf-mirror.com`，否则 huggingface.co 大概率超时。`small` 模型约 460 MB，CPU 转写速度约为音频时长的 0.5–1 倍（150 秒音频约 1.5 分钟）。

> **模型下载超时**：`small` 走镜像实测可能要 5–8 分钟，直接前台跑「下载+转写」易撞 Bash 9 分钟超时被 SIGTERM。正确姿势：先用 `huggingface_hub.snapshot_download("Systran/faster-whisper-small")`（挂镜像、前台 10 分钟超时）把模型单独下完，再跑转写；转写本身 167s 音频只要 1–2 分钟。
>
> **snapshot_download 抽风修复**：镜像 API 间歇性返回空会报 `LocalEntryNotFoundError`，但 model.bin 往往已完整落盘。修复：把缺的小文件直接下进 snapshot 目录，再改成传本地路径 `WhisperModel(<snapshot_dir>, ...)` 并设 `HF_HUB_OFFLINE=1` 彻底避开网络。
>
> **模型已缓存时可以完全离线**：`HF_HUB_OFFLINE=1` + `WhisperModel(<snapshot_dir>, ...)`，连 `initial_prompt` 都不影响速度（2026-11-02 实测 70 秒音频整条链路 21 秒跑完）。

## 转写完必做：同音错字修正

Whisper 的中文错字有固定套路，**逐字稿不能直接用**，至少过一遍：

| 常见错写 | 正确 |
|---|---|
| 牛城 / 行程（视语境） | 行程 |
| 垫赋 | 垫付 |
| 十成大海 | 石沉大海 |
| 高兴兼职 | 高薪兼职 |
| 体验室 | 体验师 |
| 食品（在招聘语境） | 直聘 |
| 何都而不为 | 何乐而不为 |
| 出门站外 | 出门在外 |
| 人事安全 | 人身安全 |
| 经济分享出来 | 经历分享出来 |
| 我的我妈 | 我和我妈 |
| 外摊大会 | 外滩大会 |
| 真正「之前」 | 真正「值钱」 |
| 特别「内」 | 特别「累」 |
| 祖先家庭 | 组建家庭 |
| 按部就班的路 | 按部就班的路 |
| 被树立为榜样 | 被树立为榜样 |
| 天专家瓦 | 添砖加瓦 |
| 长暗 | 惨案 |
| 热终于制造 | 热衷于制造 |
| 深讨 | 声讨 |
| 心疯作浪 | 兴风作浪 |
| 送容 | 容忍 |
| 自念供养 | 自恋供养 |
| 作者令人匪夷所思的事 | 做着令人匪夷所思的事 |

规律：**同音不同调、近音词、专有名词**最容易错。带 `initial_prompt` 提示主题能减少一部分。

### 拿不准的词：切片对照复听，不要瞎猜

单个 2–4 秒的存疑处，**切出来用不同 `initial_prompt` 各转一次**，
看输出是否随提示词漂移：

```bash
ffmpeg -y -loglevel error -ss 9.5 -t 3.2 -i audio.wav clip.wav
# 再用「提示含 A」「提示含 B」「无提示」「整句」四种条件各转一次，beam_size=10, temperature=0
```

- 若**所有变体都输出同一个词**（例：提示「我妈」时仍输出「我哥」）→ 该词是原词，放心用
- 若输出随提示词漂移 → 无法还原，按下面「彻底还原不出来」处理

### 语音彻底还原不出来的怎么办

有些错字听不出原词（如今天的「欺诚」→ 可能是「凄惨 / 悲情 / 惨烈」），**不要瞎猜硬填**：

1. 优先按上下文**改写整句**绕开那个词（保住意思，放弃原词）
2. 在交付时**明确列出存疑处**，让用户自己回忆原话
3. 绝不假装听清了

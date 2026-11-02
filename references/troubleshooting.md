# 排错清单

按现象自查。脚本的错误提示都是中文，且会说明「发生了什么」+「怎么办」。

## 1. 取流失败

现象：`grab_stream.py` 输出的 `url` 为空，或 `method` 是 `currentSrc-blob-or-empty`。

原因与处理（脚本已内置三条路径，依次尝试）：

| 路径 | 拿到什么 | 何时失败 |
|---|---|---|
| `performance` 过滤 `media-audio-und-mp4a` | 纯音频（最省流量） | 走 MSE 时拿不到 |
| `video.currentSrc` | 完整视频流 | 返回 `blob:` 时失效 |
| 页面 HTML 正则搜 `douyinvod` | 直链 | 页面结构变了 |

- **三条全失败** → 页面结构变动，或走了 MSE。脚本会提示：**不要加 `--headless`**（抖音对 headless 风控更严）。
- **代理环境下报 `ERR_PROXY_CONNECTION_FAILED`** → 先用 curl 测同一域名。
  代理进程活着但上游节点挂了的时候，浏览器怎么点都没用（见 `browser-automation.md` 的代理排查一节）。

## 2. 下载 403

现象：`curl` 下载视频返回 403。

原因与处理：

- **URL 签名分钟级过期** → 重新跑一次 `grab_stream.py`，拿到新 URL 立刻下载
- **缺 Referer** → 必须带 `-e "https://www.douyin.com/"`
- **User-Agent 太怪** → 用常见的桌面 Chrome UA

## 3. 「音频太短，里面大概率没有口播内容」

现象：`transcribe.py` 报时长 < 2 秒。

处理：确认这是完整视频。若视频只有十几秒且确实有人说话，多半是下载到了错误的分片——
重新取流、重新下载。

## 4. 「未检测到语音」

现象：`transcribe.py` 报 RMS 过低，或 ASR 结果为空。

这是**两种不同情况**，脚本的提示会区分：

| 情况 | 判断依据 | 处理 |
|---|---|---|
| 音频整体静音（RMS 过低） | 音量极低，阈值 0.006 | 纯音乐/纯画面视频 → 改用视频自带字幕，或向作者索取文字稿 |
| ASR 结果为空 | 音量正常但识别不出 | 音量过低或非人声 → 换更大的模型（`--model medium`）再试 |

> **注意**：视频**没有字幕轨不是错误**。本技能一律用本地语音识别，不依赖字幕。

## 5. 静音幻觉

现象：转写结果里出现大量重复的同一句话（如"谢谢大家观看"反复出现）。

原因：faster-whisper 在静音段会产生幻觉文本。

处理：脚本已内置检测（重复占比 ≥55% 判定为幻觉）并**自动去重**，同时打印提示。
剩余的零星幻觉片段，人工在对照表里删掉即可。

## 6. `vad_filter=True` 会直接崩

报错：`ImportError: ... onnxruntime_pybind11_state.so ... built for macOS 13.4 which is newer than running OS`。

原因：`onnxruntime`（VAD 的依赖）编译目标比本机 macOS 新，装不上也修不了。

处理：**`vad_filter=False` 即可绕过**——脚本已经写死为 False。
代价是静音段可能产生少量幻觉文本（见第 5 条）。

## 7. 模型下载卡住 / 失败

| 情况 | 处理 |
|---|---|
| 下载慢或超时 | 挂镜像：`HF_ENDPOINT=https://hf-mirror.com` |
| `snapshot_download` 报 `LocalEntryNotFoundError` | 镜像 API 间歇性返回空。改用本地路径：`HF_HUB_OFFLINE=1` + 直接传 snapshot 目录给 `WhisperModel` |
| `Cannot load the vocabulary` | 缺 `vocabulary.txt`（注意：**没有** `vocab.json`），补上即可 |
| 脚本报「本地没有 xxx 模型」 | 按提示先 `snapshot_download` |

**完全离线跑**（模型已缓存时）：

```bash
export HF_HUB_OFFLINE=1
python3 scripts/transcribe.py video.mp4
```

## 8. 润色结果不满意

| 现象 | 原因 | 处理 |
|---|---|---|
| 句子碎、读起来像流水账 | 断句规则太保守 | 检查 `polish.py` 的 `MIN_SENT_CHARS`（默认 18），调小会更碎、调大会更整 |
| 句子被拆在半句上 | 该片段以未完成词尾结尾，但词表没覆盖 | 把那个字加进 `INCOMPLETE_END` |
| 段落太碎 | 真实长停顿阈值太小 | 调大 `LONG_PAUSE`（默认 0.45 秒） |
| 口水词没删掉 | 不在词表里 | 加进 `FILLERS_TONE` / `FILLERS_MARKER` |
| 误删了有意义的词 | 该词被当成语气词 | 用 `--keep-fillers` 关掉删除，或把它从词表移出 |
| 同音错字没改 | 设计如此 | 属 ASR 识别问题，用 `--prompt` 给题材，或人工订正 |

## 9. 逐字稿和视频对不上

现象：某些句子缺失或顺序不对。

- 缺失 → 检查下载的是不是完整视频（`ffprobe` 看时长）
- 顺序错乱 → 换 `--model medium` 重跑，或人工对照视频订正
- 开头结尾少一截 → 抖音分享页有时会截取首尾，改用桌面 UA 或带 Referer 重新下载

## 10. 脚本报缺依赖

| 缺失 | 安装 |
|---|---|
| `faster_whisper` | `pip install faster-whisper` |
| `playwright` | `pip install playwright`（**不需要** `playwright install`） |
| ffmpeg | `brew install ffmpeg` / `apt install ffmpeg` |

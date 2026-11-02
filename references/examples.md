# 使用示例

## 场景一：完整流程（链接 → 逐字稿 + 润色稿）

```bash
# 1) 短链 → video_id
curl -s -o /dev/null -w "%{url_effective}\n" -L -m 20 \
  -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  "https://v.douyin.com/XXXXXX/"
# → https://www.iesdouyin.com/share/video/7625254284757699891/...

# 2) 取流（顺带拿作者信息，确认是自己的视频）
python3 scripts/grab_stream.py 7625254284757699891
# → {video_id, url, method, meta, video_duration}

# 3) 下载（URL 分钟级过期，立刻下）
curl -s -L -m 180 -o video.mp4 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36" \
  -e "https://www.douyin.com/" "<上一步的 url>"

# 4) 转写
python3 scripts/transcribe.py video.mp4 --out-dir . --model small \
  --prompt "以下是关于<题材>的普通话口播逐字稿。"

# 5) 润色
python3 scripts/polish.py transcript_raw.txt --out-dir . --title "<视频标题>"

# 6) 复核（必做）
cat transcript_diff.md
```

## 场景二：只润色已有逐字稿

```bash
python3 scripts/polish.py 别人的逐字稿.txt --out-dir ./out --title "标题"
```

输入是 txt 时，若同目录存在 `transcript_segments.json` 会自动优先使用（断句更准）。

## 场景三：只要逐字稿，不要润色

```bash
python3 scripts/transcribe.py video.mp4 --out-dir .
# 产出 transcript_raw.txt + transcript_segments.json
```

## 场景四：语速快 / 专有名词多

```bash
# 给题材提示，能显著减少同音错字
python3 scripts/transcribe.py video.mp4 --prompt "以下是关于NPD自恋型人格障碍、原生家庭、创伤觉醒的普通话口播逐字稿。"

# 换更大的模型
python3 scripts/transcribe.py video.mp4 --model medium
```

## 一次真实跑通记录（2026-11-02）

素材：一条 70.4 秒的抖音口播视频（720×1280 / 11.79 MB）。

| 环节 | 实测 |
|---|---|
| 取流 | `video.currentSrc` 命中（performance 未命中音频流） |
| 转写 | faster-whisper small 离线，**28 段 / 328 字**，70 秒音频耗时约 21 秒 |
| 词级时间戳 | 启用（`word_timestamps=True`），用于判断真实停顿 |
| 润色 | 28 段 → 13 句 → 2 段；补标点 13 处；删冗余 0 处（这条视频语速快、几乎没有口水词） |
| 完整性校验 | 原文 328 字（去标点）**全部出现在润色稿中，零丢失** ✓ |

**这次实跑暴露的三个问题（已修）**

1. **断句太碎**：最初把每个 ASR 片段都当成独立句子，输出像流水账
   → 加入「短片段合并」+「未完成词尾不断句」两条规则
2. **段落切不出来**：faster-whisper 关了 VAD 后，片段之间的时间间隔全是 0.00 秒，无法用停顿分段
   → 改用**词级时间戳**（`word_timestamps=True`）计算词间真实静音
3. **tail 分支丢内容**：`joined = joined if not joined else ...` 三元写反，最后几句被丢掉
   → 回归测试发现并修复，加了"原文所有字必须出现在润色稿中"的完整性校验

## 脚本参数速查

```bash
# grab_stream.py
python3 scripts/grab_stream.py <VIDEO_ID> [--out stream_result.json] [--headless] [--wait 9]

# transcribe.py
python3 scripts/transcribe.py <媒体文件> [--out-dir .] [--model small] [--language zh]
                               [--prompt "题材提示"] [--keep-wav]

# polish.py
python3 scripts/polish.py <逐字稿> [--out-dir .] [--title "标题"] [--keep-fillers] [--diff-only]
```

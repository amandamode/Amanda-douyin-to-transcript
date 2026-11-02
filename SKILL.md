---
name: douyin-to-transcript
display_name: 抖音口播转逐字稿
display_name_en: Douyin Speech to Transcript
description: 输入一条抖音视频链接，提取口播逐字稿（本地语音识别，不依赖视频字幕轨），并做规则式润色：去口语冗余、修正断句、补全标点、整理段落，但不改原意。当用户说「把这个抖音视频转成逐字稿」「这个视频讲了什么」「帮我把口播整理成文字」「逐字稿润色一下」时使用。
description_zh: 把抖音口播视频转成可用的文字稿：本地语音识别出逐字稿，再做去冗余、断句、标点、分段的规则式润色，并附原文对照表便于复核。
description_en: Turn a Douyin short-video into a usable transcript — local speech recognition plus rule-based polishing (filler removal, sentence breaks, punctuation, paragraphing) with a side-by-side diff so nothing was changed in meaning.
examples_zh:
- "把这个抖音链接转成逐字稿：https://v.douyin.com/XXXXXX/"
- "这个视频讲了什么？给我一份文字稿"
- "帮我把这段口播的逐字稿润色一下，去掉口水词、补好标点分段"
examples_en:
- "Turn this Douyin link into a transcript: https://v.douyin.com/XXXXXX/"
- "What does this video say? Give me the text"
- "Polish this transcript: drop the filler words and fix the punctuation"
version: 1.0.1
author: Amanda
allowed-tools: Bash, Read
---

# 抖音口播 → 逐字稿（提取 + 润色）

输入一条抖音视频链接，输出**逐字稿**与**润色稿**两份文字，并附原文对照表。

## 元信息

| 项 | 值 |
|---|---|
| 技能标识 | `douyin-to-transcript` |
| 版本 | 1.0.1 |
| 作者 | Amanda |
| 许可证 | MIT |
| 仓库 | 待建（GitHub 仓库名建议 `Amanda-douyin-to-transcript`） |
| 运行环境 | macOS / Linux · Python 3.9+ · ffmpeg · Google Chrome · faster-whisper |
| 依赖声明 | `requirements.txt` |
| 抓流实现 | `@references/transcribe.md` |
| 润色规则 | `@references/polish.md` |
| 排错 | `@references/troubleshooting.md` |

## 何时使用

- 用户发来抖音/短视频链接，要求「转成逐字稿」「这个视频讲了什么」「整理成文字」
- 用户手上有一份口播逐字稿（ASR 输出），要求「润色」「去口水词」「补标点分段」

**不适用**：需要把内容变成公众号文章并推送草稿箱 → 用 `douyin-to-wechat-draft`；
需要字幕文件（SRT/VTT）→ 本技能只出纯文本。

> ⚠️ **与 `douyin-to-wechat-draft` 的关系**：本技能是它的**前半段拆分版**
> （取流 + 转写 + 润色）。两者共用同一套 `grab_stream.py`，输出格式一致，
> 可以直接拼接：`douyin-to-transcript` 的润色稿 → `douyin-to-wechat-draft` 的配图与推送环节。
> 本机若同时装有旧的 `douyin-transcript`（依赖已失效的 `agent-browser`），
> **建议替换成这个**，避免触发词撞车。

## 输入与输出

**输入**：一个抖音链接（`v.douyin.com/...` 或 `douyin.com/video/...`）+ 可选的主题提示。

**输出**（默认写在当前工作目录）：

| 文件 | 内容 |
|---|---|
| `transcript_raw.txt` | 原始逐字稿（ASR 直出，无标点） |
| `transcript_segments.json` | 分段数据：起止时间、段前静音、逐词时间戳 |
| `transcript_polished.md` | 润色稿（去冗余 + 断句 + 标点 + 分段） |
| `transcript_diff.md` | 原文 ↔ 润色对照表 + 删掉的词清单（**复核用**） |
| `polish_report.json` | 统计：字数变化、段落数、删词数、补标点数 |

## 执行流程

### 1. 解析链接 + 取流地址

```bash
# 短链 → video_id
curl -s -o /dev/null -w "%{url_effective}\n" -L -m 20 \
  -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  "https://v.douyin.com/XXXXXX/"

# 浏览器内取流地址（拿到 url 与作者信息）
python3 scripts/grab_stream.py <VIDEO_ID>
```

**必须用浏览器取流**：抖音的分享页与开放接口都已封死，详见 `@references/transcribe.md`。
`grab_stream.py` 的输出里 `meta` 字段含作者昵称与点赞数——**先确认是用户自己的视频**
（他人内容涉及版权，不做转写）。

### 2. 下载并转写

```bash
# 立刻下载（URL 分钟级过期，必须带 Referer）
curl -s -L -m 180 -o video.mp4 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36" \
  -e "https://www.douyin.com/" "<上一步的 url>"

# 转写（自动转码 + 语音识别 + 异常检测）
python3 scripts/transcribe.py video.mp4 --out-dir . \
  --model small \
  --prompt "以下是关于<题材>的普通话口播逐字稿。"
```

`--prompt` 写上题材能明显减少同音错字（实测「NPD/原生家庭」这类专有名词必须给提示）。

### 3. 润色

```bash
python3 scripts/polish.py transcript_raw.txt --out-dir . --title "<视频标题>"
```

只做四件事，**不改原意**：去口语冗余 → 修正断句 → 补全标点 → 整理段落。
规则与词表见 `@references/polish.md`。

### 4. 人工复核（别跳过）

```bash
cat transcript_diff.md      # 原文 ↔ 润色对照 + 删词清单
```

对照表会明确列出**删掉了哪些词**，并给出规则式润色的局限说明。
确认没有实词被动过，再交付。

**特别提醒**：同音错字（如「深讨/声讨」「送容/容忍」）属于 **ASR 识别问题**，
本技能**不会自动改**——规则式改字有改错的风险，这类订正请在复核时人工处理。

### 5. 交付

回复中给出：视频标题与时长、逐字稿字数、润色稿字数与段落数、
**改动了什么**（删词数 / 补标点数）、输出文件路径，以及**存疑的字词清单**。

## 依赖与限制

### 依赖

| 依赖 | 说明 |
|---|---|
| ffmpeg | 音频转码（`-vn -ac 1 -ar 16000 -c:a pcm_s16le`） |
| faster-whisper | 本地语音识别；`vad_filter=False`（见 `references/transcribe.md` 的坑） |
| playwright + Google Chrome | 抓流地址；用 `channel="chrome"` 驱动系统 Chrome，**无需下载内核** |
| Python 3.9+ | 运行脚本（`polish.py` 纯标准库；`transcribe.py` 需要 faster-whisper） |

### 限制

- **不依赖视频字幕轨**：一律本地语音识别。视频没有字幕**不是问题**；视频没有**语音**才是。
- **识别质量受模型限制**：`small` 模型在快语速、口音重、背景音大时会出错；同音错字需人工订正。
- **规则式润色有边界**：断句依据是停顿与片段边界，语义上应该断开的地方可能切得不理想；
  详见 `@references/polish.md` 的"局限"一节。
- **不扩写、不改写、不翻译、不摘要**：只做那四件事。
- **抓流 URL 分钟级过期**：拿到立刻下载；失效就重新取一次流。
- **只有首次运行要下模型**（`small` 约 460MB，建议挂镜像）；之后可离线跑。

## 异常提示（脚本已内置）

| 情况 | 脚本行为 |
|---|---|
| 链接无效 / 解析不出 video_id | 提示链接格式要求，不进入下载 |
| 取流三条路径全失败 | 明确说明已尝试的三条路径，并给出 headless 禁忌与代理排查提示 |
| 下载 403 | 提示签名过期（重新取流）或缺 Referer |
| 音轨缺失 / 时长 < 2 秒 | 明确报「音频太短，大概率没有口播内容」 |
| **整体静音（RMS 过低）** | 明确报「未检测到语音」，建议改用字幕或索取文字稿 |
| **ASR 结果为空** | 明确报「未检测到语音」 |
| 静音幻觉（重复占比高） | 自动去重并提示 |
| faster-whisper 未装 / 模型未下载 | 给出对应安装命令（区分两种情况） |

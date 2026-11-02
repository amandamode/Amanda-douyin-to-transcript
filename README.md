# 抖音口播转逐字稿（douyin-to-transcript）

输入一条抖音视频链接，输出**逐字稿**与**润色稿**两份文字，并附原文对照表。

**去口语冗余 · 修正断句 · 补全标点 · 整理段落 —— 但不改原意。**

| 元信息 | 值 |
|---|---|
| 技能标识 | `douyin-to-transcript` |
| 版本 | 1.0.0 |
| 作者 | Amanda |
| 许可证 | MIT |
| 运行环境 | macOS / Linux · Python 3.9+ · ffmpeg · Google Chrome · faster-whisper |
| 依赖 | `requirements.txt`（polish 部分纯标准库） |

## 功能特性

- **本地语音识别**：不依赖视频字幕轨，音频不出本机，模型可离线跑
- **浏览器内取流**：抖音的分享页与开放接口都已封死，只有在真实浏览器里执行 JS 才拿得到流地址
- **规则式润色**：去口水词、断句、补标点、分段——**确定性规则，不调用模型**，同样的输入永远同样的输出，可审查可争论
- **完整性保证**：每次运行都产出**原文 ↔ 润色对照表**与删词清单，交付前一眼就能确认"没动原意"
- **异常处理到位**：链接无效 / 无语音 / 无音轨 / 静音幻觉 / 模型未下载，各有明确中文提示与处置办法

## 安装

```bash
git clone <仓库地址> && cd douyin-to-transcript
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**系统依赖**：`ffmpeg`（音频转码）、`Google Chrome`（抓流）。
脚本用 `channel="chrome"` 驱动系统 Chrome，**不需要** `playwright install` 下载内核。

放进技能目录即可被 WorkBuddy 识别：

```bash
ln -s "$(pwd)/douyin-to-transcript" ~/.workbuddy/skills/douyin-to-transcript
```

## 配置

可选，全部有合理默认值（见 `config.example.env`）：

| 配置项 | 默认 | 说明 |
|---|---|---|
| `WHISPER_MODEL` | `small` | tiny / base / small / medium / large |
| `WHISPER_LANGUAGE` | `zh` | 语言代码 |
| `WHISPER_PROMPT` | 空 | **题材提示**，给上能显著减少同音错字 |
| `HF_ENDPOINT` | 镜像地址 | 首次下模型用 |
| `HF_HUB_OFFLINE` | 未设 | 设成 `1` 则完全离线跑 |

## 调用示例

**对话触发**：

```
把这个抖音链接转成逐字稿：https://v.douyin.com/XXXXXX/
这个视频讲了什么？给我一份文字稿
帮我把这段口播的逐字稿润色一下，去掉口水词、补好标点分段
```

**手动调脚本**：

```bash
# 1) 取流（同时拿作者信息）
python3 scripts/grab_stream.py <VIDEO_ID>

# 2) 下载（URL 分钟级过期，必须带 Referer）
curl -s -L -m 180 -o video.mp4 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36" \
  -e "https://www.douyin.com/" "<上一步的 url>"

# 3) 转写
python3 scripts/transcribe.py video.mp4 --out-dir . --model small --prompt "以下是关于<题材>的普通话口播逐字稿。"

# 4) 润色
python3 scripts/polish.py transcript_raw.txt --out-dir . --title "<视频标题>"

# 5) 复核（必做）
cat transcript_diff.md
```

## 输出

| 文件 | 内容 |
|---|---|
| `transcript_raw.txt` | 原始逐字稿（ASR 直出，无标点） |
| `transcript_segments.json` | 分段数据：起止时间、段前静音、逐词时间戳 |
| `transcript_polished.md` | 润色稿 |
| `transcript_diff.md` | 原文 ↔ 润色对照表 + 删掉的词清单 |
| `polish_report.json` | 统计：字数变化、段落数、删词数、补标点数 |

## 目录结构

```
douyin-to-transcript/
├── SKILL.md                      # ★ 技能定义（frontmatter + 步骤 + 依赖与限制）
├── README.md                     # 本文件
├── LICENSE                       # MIT
├── CONTRIBUTING.md               # 贡献指南
├── CHANGELOG.md                  # 变更记录
├── requirements.txt              # 依赖声明
├── config.example.env            # 配置模板（占位符，无密钥）
├── .gitignore
├── references/                   # 详细实现（SKILL.md 用 @references/xxx.md 引用）
│   ├── transcribe.md             # 取流 + 转写的完整链路与三个坑
│   ├── polish.md                 # 润色规则详解（词表、断句规则、局限）
│   ├── troubleshooting.md        # 排错清单
│   ├── examples.md               # 使用示例 + 一次真实跑通记录
│   └── faq.md                    # 常见问题
├── scripts/                      # 可执行脚本
│   ├── grab_stream.py            # 浏览器内取流（Playwright + 系统 Chrome）
│   ├── transcribe.py             # 转写（含异常检测）
│   └── polish.py                 # 规则式润色（纯标准库）
└── templates/
    └── transcript.md             # 输出模板
```

## 它和 `douyin-to-wechat-draft` 的关系

后者是**全流程**（取流 → 转写 → 润色 → 配图 → HTML → 推微信公众号草稿箱）；
本技能只做**前半段**，不碰配图与推送。

两者共用同一个 `grab_stream.py`，输出格式完全一致——
所以本技能的 `transcript_polished.md` 可以直接喂给 `douyin-to-wechat-draft` 的后半段。
若两个都装，注意触发词重叠（两者都以「抖音链接 → 逐字稿」为入口），建议只用一个。

> 本机若还装着早期的 `douyin-transcript`（依赖 `agent-browser` 命令，该命令在多数机器上并不存在），
> **建议用本技能替换它**，否则会在取流这一步卡住。

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。贡献流程见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

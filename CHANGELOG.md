# 变更记录

## v1.0.1 — 2026-11-02

**防御性修复（对标开放平台「内置文件缺失」驳回）**

- `README.md`：把说明性占位 `references/xxx.md` 改为不带路径 token 的写法，规避字面路径被平台扫描误判为缺失文件
- `SKILL.md` / `README.md`：`version` → 1.0.1

## v1.0.0 — 2026-11-02

首个发布版。从 `douyin-to-wechat-draft` 拆分出的**前半段**：取流 → 转写 → 润色。

### 新增
- `scripts/transcribe.py` — 音频/视频 → 逐字稿（本地 ASR）。
  内置异常检测并给出明确中文提示：
  ① 文件不存在 / 非媒体文件 ② ffmpeg 不可用 ③ 音轨缺失或时长 < 2 秒
  ④ **整体静音（RMS 过低）→ 报「未检测到语音」** ⑤ **ASR 结果为空 → 报「未检测到语音」**
  ⑥ faster-whisper 未安装 / 模型未下载（两种情况分别给对应命令）
  ⑦ 静音幻觉自动检测与去重。
  启用 `word_timestamps=True`，输出逐词时间戳与段前静音，供润色判断段落边界。
- `scripts/polish.py` — 规则式润色（纯标准库）。只做四件事：
  去口语冗余 / 修正断句 / 补全标点 / 整理段落；**不删任何实词、不改语序、不扩写**。
  输出润色稿 + 原文对照表 + 删词清单 + 统计。
- `references/polish.md` — 润色规则详解：口语词表、断句规则（含未完成词尾表）、
  标点补全条件、段落划分依据，以及**规则式润色的局限**（断句不是语义理解；同音错字不自动改）。
- `references/troubleshooting.md` — 按现象自查的排错清单（10 类）。
- `references/examples.md` — 使用场景 + 参数速查 + 一次真实跑通记录与三个已修问题的复盘。
- `references/faq.md` — 常见问题。
- `requirements.txt` / `config.example.env` / `CONTRIBUTING.md` / `CHANGELOG.md` /
  `templates/transcript.md` — 依赖声明、配置模板、贡献指南、变更记录、输出模板。

### 复用（与 `douyin-to-wechat-draft` 保持一致）
- `scripts/grab_stream.py` — 逐字节复用，两个技能的取流行为完全一致
- `references/transcribe.md` — 复用并对齐步骤编号
- `LICENSE` / `.gitignore` — 复用

### 实跑验证（2026-11-02，真实抖音视频）
70.4 秒视频 → 28 段 / 328 字 → 润色后 13 句 / 2 段；**原文所有字均出现在润色稿中，零丢失** ✓

### 实跑中发现并修复的三个问题
1. **断句太碎**：最初把每个 ASR 片段都当成独立句子 → 加入「短片段合并」与
   「未完成词尾（`INCOMPLETE_END`）不断句」两条规则
2. **段落切不出来**：faster-whisper 关 VAD 后片段间隔全是 0.00 秒 → 改用**词级时间戳**计算真实静音
3. **tail 分支丢内容**：`joined = joined if not joined else ...` 三元写反导致末尾几句被静默丢弃
   → 修复，并加入"原文所有字必须出现在润色稿中"的硬性回归门槛

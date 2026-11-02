# 贡献指南

## 环境准备

```bash
git clone <仓库地址> && cd douyin-to-transcript
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

系统依赖：`ffmpeg`、Google Chrome（脚本用 `channel="chrome"` 驱动系统 Chrome，
**不需要** `playwright install`）。

## 本地开发与自检

改完必跑：

```bash
# 1. 语法
python3 -m py_compile scripts/*.py

# 2. 每个脚本的 --help 都要正常
for s in scripts/*.py; do python3 "$s" --help >/dev/null || echo "FAIL $s"; done

# 3. 端到端自测（用一条自己的短视频）
python3 scripts/grab_stream.py <VIDEO_ID>          # 取流
python3 scripts/transcribe.py video.mp4 --out-dir . # 转写
python3 scripts/polish.py transcript_raw.txt --out-dir .  # 润色

# 4. 完整性校验：原文每个字都必须出现在润色稿里
python3 - <<'PY'
import re
raw = re.sub(r"[，。？！、,.!?\s]", "", open("transcript_raw.txt",encoding="utf-8").read())
pol = re.sub(r"[，。？！、,.!?\s#>「」（）()\n]", "", open("transcript_polished.md",encoding="utf-8").read())
missing = [c for c in set(raw) if c not in pol]
print("丢失的字:", missing if missing else "无 ✓")
assert not missing, "润色稿丢了原文的字 —— 属于严重回归"
PY
```

> 第 4 步是**硬性回归门槛**：润色只允许删词表内的口水词，不允许丢任何实词。
> 曾经有个三元表达式写反的 bug 导致末尾几句被静默丢弃，就是靠这一步抓出来的。

## 改润色规则时

判断依据集中在 `references/polish.md` 与 `scripts/polish.py` 顶部的常量：

| 常量 | 作用 | 什么时候调 |
|---|---|---|
| `FILLERS_TONE` / `FILLERS_MARKER` / `FILLERS_EN` | 口语冗余词表 | 想多删/少删某些口头语 |
| `INCOMPLETE_END` | 未完成词尾表 | 断句切在半句上时 |
| `MIN_SENT_CHARS` | 一句最少多少字 | 句子太碎 / 句子太长 |
| `LONG_FRAGMENT` | 单片段自成一句的阈值 | 长片段被拼在一起 |
| `LONG_PAUSE` | 段落边界的长停顿阈值 | 段落太碎 / 段落太粗 |
| `TARGET_PARA_CHARS` | 每段目标字数 | 段落长度不合适 |

**改任何一条都要同步更新 `references/polish.md`**，并在 PR 里说明改动理由与实测效果。

## 提交规范

[Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 新增能力
fix: 修 bug
docs: 只改文档
refactor: 不改行为的重构
chore: 构建/配置/杂项
```

## 红线（绝对不能）

| 红线 | 说明 |
|---|---|
| **润色丢实词** | 只允许删词表内的口水词。任何"让输出更通顺"的重写都不行——那会改变原意 |
| **自动改同音错字** | 规则式改字会把对的改成错的。同音错字属 ASR 识别问题，靠 `--prompt` 与人工订正解决 |
| **把抓流写回 agent-browser** | 该命令在多数机器上不存在，本技能用自带的 `grab_stream.py` |
| **在本机绝对路径** | 不能出现用户目录绝对路径 |
| **写自己的违规样例** | 别把完整的违规代码写进源码——静态扫描会命中它自己 |

## 版本与发布

语义化版本：

| 变更 | 版本位 |
|---|---|
| 修 bug、改文案 | PATCH `1.0.1` |
| 新增能力（新的脚本、新的输出） | MINOR `1.1.0` |
| 破坏性变更（输出格式变化、参数改名） | MAJOR `2.0.0` |

发布流程：

1. 更新 `SKILL.md` 的 `version` 与 `CHANGELOG.md`
2. `git commit -am "release: v1.1.0"` + `git tag -a v1.1.0` + `git push --tags`
3. 重新打包 zip（首层为技能目录且含 `SKILL.md`），发 Release 供他人下载

## 提 issue 请带

- 操作系统 + Python 版本
- 完整命令与完整报错
- 若涉及识别问题：贴 `transcript_segments.json` 里的对应片段
- **不要贴任何密钥**，贴前先打码

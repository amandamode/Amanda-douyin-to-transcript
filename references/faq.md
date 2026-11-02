# 常见问题（FAQ）

## 提取

**Q：这个技能能处理没有字幕的视频吗？**
A：能，而且**本来就不依赖字幕**。它用本地语音识别（faster-whisper）转写，
视频有没有字幕轨都一样。真正做不到的是"视频里没有语音"。

**Q：视频是别人的，能用吗？**
A：技术上可以，但涉及版权。`grab_stream.py` 的输出里 `meta` 字段有作者昵称，
先确认是不是用户自己的内容。

**Q：为什么不用 yt-dlp？**
A：实测报 `Fresh cookies (not necessarily logged in) are needed`，
而且 yt-dlp 也不处理抖音的签名规则。详见 `transcribe.md` 的"不要走的路"。

**Q：抓流要多久？**
A：打开页面约 5 秒 + 播放 9 秒（让媒体资源进 performance），总共 20 秒内。

**Q：流地址能重复用吗？**
A：不能，分钟级过期。拿到立刻下载；403 就重新取一次。

## 转写

**Q：模型要下多大？**
A：`small` 约 460MB，`tiny` 约 75MB，`medium` 约 1.5GB。首次下载后可以完全离线跑。

**Q：速度多快？**
A：CPU + int8 实测约为音频时长的 0.3–1 倍。70 秒音频约 21 秒转完。

**Q：识别不准怎么办？**
A：按性价比排序：① 加 `--prompt` 给题材（专有名词错得最多时最有效）
② 换 `--model medium` ③ 人工对照视频订正。

**Q：为什么不用 `vad_filter=True`？**
A：它的依赖 `onnxruntime` 在部分 macOS 上装不上（编译目标比系统新），
报错会直接崩。脚本写死 `vad_filter=False`，代价是静音段可能有少量幻觉（脚本会自动去重）。

## 润色

**Q：润色会不会改了我的意思？**
A：不会。脚本只做四件事（去词表内的口水词、断句、补标点、分段），**不删任何实词、不改语序、不扩写**。
每次运行都产出 `transcript_diff.md`，里面列清楚删了哪些词——交付前扫一眼即可确认。

**Q：同音错字会自动改吗？**
A：**不会**，而且刻意不改。"深讨/声讨"、"送容/容忍"这类是 ASR 识别错误，
规则式改字有改错的风险（把对的改成错的）。处理方式：用 `--prompt` 给题材从源头减少，或人工订正。

**Q：为什么断句不是我想要的位置？**
A：规则式断句依据的是**停顿与片段边界**，不是语义理解。
遇到"语义该断但语流连贯"的地方会切得不理想。可以调 `scripts/polish.py` 顶部的
`MIN_SENT_CHARS`（句子长度）、`LONG_PAUSE`（停顿阈值）、`INCOMPLETE_END`（未完成词尾表）。

**Q：能只做断句标点、不删词吗？**
A：加 `--keep-fillers`。

**Q：段落是怎么分出来的？**
A：两个依据——① 句子前有 ≥0.45 秒真实静音（说话人换气）② 累计到 260 字。
静音来自词级时间戳，所以是**客观信号**，不是猜的。

**Q：润色后字数变多了？**
A：正常。补标点会加进几十个字，删词通常减不了多少，净变化一般是正的。统计见 `polish_report.json`。

## 输出

**Q：产出哪些文件？**
A：`transcript_raw.txt`（原始逐字稿）、`transcript_segments.json`（分段+词级时间戳）、
`transcript_polished.md`（润色稿）、`transcript_diff.md`（对照表）、
`polish_report.json`（统计）。

**Q：能只给逐字稿吗？**
A：只跑 `transcribe.py` 即可；或给 `polish.py` 加 `--diff-only`。

## 与别的技能的关系

**Q：和 `douyin-to-wechat-draft` 有什么区别？**
A：后者是**全流程**（取流 → 转写 → 润色 → 配图 → HTML → 推微信公众号草稿箱）；
本技能只做**前半段**（取流 → 转写 → 润色），不碰配图与推送。
两者共用同一个 `grab_stream.py`，输出格式完全一致，
所以本技能的 `transcript_polished.md` 可以直接喂给 `douyin-to-wechat-draft` 的后半段。

**Q：和旧的 `douyin-transcript` 有什么区别？**
A：旧版是早期手写版，只有 SKILL.md 没有脚本，且依赖 `agent-browser` 命令——
该命令在大多数机器上**并不存在**，跑起来会卡在取流这一步。
本版本改用自带的 `scripts/grab_stream.py`（Playwright 驱动系统 Chrome），自包含、装上即用。
**建议直接用新版替换旧版**，避免触发词撞车。

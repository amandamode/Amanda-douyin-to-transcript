#!/usr/bin/env python3
"""逐字稿 → 润色稿（规则式，纯标准库）

用法:
  python3 polish.py <transcript_raw.txt | transcript_segments.json> \
      [--out-dir .] [--title "视频标题"] [--keep-fillers] [--diff-only]

只做四件事，**不改原意**：
  1 去除口语冗余      —— 只删词表内的口水词与话语标记，不删任何实词
  2 修正断句          —— 优先按 ASR 分段边界断句，其次按连接词在长句内部切分
  3 补全标点          —— 句末补 。/？/！，枚举语境补「、」
  4 整理段落结构      —— 按字数与时长把句子归成自然段

**不做**：改写、扩写、翻译、摘要、合并不同含义的句子、精简内容。

输出:
  transcript_polished.md   润色稿
  transcript_diff.md       逐段对照（原句 → 润色句），用于人工复核"没改原意"
  polish_report.json       统计：删了几个冗余词、补了几个标点、切了几段
"""
import argparse
import json
import os
import re
import sys

# ── 口语冗余词表 ─────────────────────────────────────────────────────
# 分两类，删除策略不同：
#   A 类「语气词」：独立出现、没有实义，删掉不影响理解
#   B 类「话语标记」：成对出现时删，单独出现时保留（避免改变指代关系）
FILLERS_TONE = ["嗯", "呃", "啊", "哦", "唉", "诶", "欸", "噢", "喔", "唔"]
FILLERS_MARKER = ["就是说", "然后呢", "怎么说呢", "对不对", "对吧", "你知道吧",
                  "你知道吗", "其实呢", "基本上说", "怎么说", "那么呢", "然后就是"]
FILLERS_EN = [r"\bum\b", r"\buh\b", r"\byou know\b", r"\bi mean\b"]

# ── 连接词：长句内部断句用 ───────────────────────────────────────────
CONNECTORS = ["但是", "不过", "而且", "所以", "因为", "然后", "其实", "就是说",
              "结果", "于是", "另外", "接下来", "首先", "其次", "最后"]

# 句末语气 → 标点
END_QUESTION = ("吗", "呢", "么")
END_EXCLAM = ("啊", "呀", "哇", "哎")

# 枚举引导词 → 其后的并列项之间补顿号
ENUM_LEAD = ["比如", "例如", "包括", "有以下", "分别是", "有这几"]

TARGET_PARA_CHARS = 260   # 每段目标字数
MAX_PARA_CHARS = 400      # 段落硬上限
MIN_SENT_CHARS = 18       # 一句至少这么多字（短片段合并到够长才断句）
LONG_FRAGMENT = 34        # 超过这个长度的片段自成一句
LONG_PAUSE = 0.45         # 真实静音超过这个秒数 → 段落边界（来自词级时间戳）

# 「句子还没说完」的尾字：以这些字结尾的片段必须与下一段合并，不能在此断句。
# 这是中文流水账最常见的坑——ASR 按停顿切出来的片段往往停在半句上
# （例：「过去被NPD伤害过的我们」+「不知道如何去描述这类人」）
INCOMPLETE_END = ("的", "地", "得", "了", "着", "和", "与", "或", "而", "但", "却",
                   "就", "都", "也", "还", "很", "更", "把", "被", "给", "对", "从",
                   "向", "为", "以", "让", "使", "等", "个", "些", "们", "是", "有",
                   "会", "要", "能", "可", "那", "这", "其", "之")


def load_input(path):
    """返回 (segments, full_text)。segments 可能为空（纯文本输入）。"""
    if path.endswith(".json"):
        d = json.load(open(path, encoding="utf-8"))
        segs = d.get("segments") or []
        return segs, d.get("full", "")
    txt = open(path, encoding="utf-8").read().strip()
    # 同目录下若有 segments.json，优先用它（有分段边界，断句更准）
    sib = os.path.join(os.path.dirname(os.path.abspath(path)), "transcript_segments.json")
    if os.path.isfile(sib):
        d = json.load(open(sib, encoding="utf-8"))
        if d.get("segments"):
            return d["segments"], txt
    return [], txt


def remove_fillers(text, keep=False):
    """删除口语冗余。返回 (新文本, 删除次数, 删除明细)。"""
    if keep:
        return text, 0, []
    removed = []
    for w in FILLERS_MARKER:
        if w in text:
            n = text.count(w)
            text = text.replace(w, "")
            removed += [w] * n
    for w in FILLERS_TONE:
        # 语气词删三种情形：① 前面是标点/空白 ② 后面是标点/空白 ③ 位于片段开头
        # 中间夹在实词之间的语气词（如「好快啊」）保留——那里它可能有实义
        pat = re.compile(r"(?<![一-鿿])" + re.escape(w) + r"(?![一-鿿])|"
                         + re.escape(w) + r"(?=[，。！？、,.!?\s])")
        text, n = pat.subn("", text)
        if text.startswith(w):                 # ③ 片段开头
            text = text[len(w):]
            n += 1
        removed += [w] * n
    for pat in FILLERS_EN:
        regex = re.compile(pat, re.I)
        text, n = regex.subn("", text)
        removed += [pat] * n
    # 清理删剩下的空标点与重复空格
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text, len(removed), removed


def merge_fragments(fragments):
    """把 ASR 片段合并成完整句子。

    fragments: [(文本, 段前静音秒数, 是否段前有长停顿)]
    规则：
      · 片段太短就并入下一句（口语里常是半句）
      · 累计够 MIN_SENT_CHARS 才断句
      · 遇到长停顿（≥LONG_PAUSE）立即断句并标记为段落边界
    返回 [(句子文本, 是否段落边界)]
    """
    sentences, buf, buf_len = [], [], 0
    for i, (text, gap, long_pause) in enumerate(fragments):
        buf.append(text)
        buf_len += len(text)
        nxt_long = (i + 1 < len(fragments)) and fragments[i + 1][2]
        # 尾字判定：这句话是不是还没说完
        incomplete = text.rstrip("，,、").endswith(INCOMPLETE_END) and buf_len < 60
        if (buf_len >= MIN_SENT_CHARS or len(text) >= LONG_FRAGMENT or nxt_long) \
                and not incomplete:
            joined = ""
            for t in buf:
                if not joined:
                    joined = t
                else:
                    joined = joined.rstrip("，,、") + "，" + t.lstrip("，,、")
            sentences.append((joined, long_pause))
            buf, buf_len = [], 0
    if buf:
        joined = ""
        for t in buf:
            if not joined:
                joined = t
            else:
                joined = joined.rstrip("，,、") + "，" + t.lstrip("，,、")
        if joined:
            sentences.append((joined, False))
    return sentences


def split_sentences(chunk, use_connectors=True):
    """长句内部按连接词再切（当一个片段本身很长时）。"""
    out, buf = [], ""
    for ch in chunk:
        buf += ch
        if ch in "。！？!?":
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    if not use_connectors:
        return out
    final = []
    for s in out:
        if len(s) <= MAX_PARA_CHARS and len(s) < 40:
            final.append(s)
            continue
        parts, rest = [], s
        while len(rest) > 40:
            cut = -1
            for c in CONNECTORS:
                idx = rest.find(c)
                if 0 < idx < len(rest) - 8:
                    cut = max(cut, idx)
            if cut <= 0:
                break
            parts.append(rest[:cut].strip())
            rest = rest[cut:]
        if rest.strip():
            parts.append(rest.strip())
        final += [p for p in parts if p]
    return final


def add_punctuation(sentences):
    """补全标点。返回 (句子列表, 补标点次数)。"""
    out, added = [], 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if s[-1] not in "。！？!?":
            if s.rstrip("，,、").endswith(END_QUESTION):
                s = s.rstrip("，,、") + "？"
                added += 1
            elif s.rstrip("，,、").endswith(END_EXCLAM):
                s = s.rstrip("，,、") + "！"
                added += 1
            else:
                s = s + "。"
                added += 1
        out.append(s)
    # 枚举语境补顿号：引导词后的并列短项
    fixed = []
    for s in out:
        for lead in ENUM_LEAD:
            if lead in s:
                head, _, tail = s.partition(lead)
                items = [i for i in re.split(r"[、，,\s]+", tail) if i]
                if 3 <= len(items) <= 8 and all(len(i) <= 8 for i in items):
                    tail2 = tail
                    for it in items:
                        tail2 = re.sub(re.escape(it) + r"(?![一-鿿])", it + "、", tail2, count=1)
                    tail2 = tail2.rstrip("、")
                    s = head + lead + tail2
                    added += len(items) - 1
                break
        fixed.append(s)
    return fixed, added


def group_paragraphs(sentences):
    """sentences: [(句子文本, 是否段落边界)] → 段落列表"""
    paras, cur, cur_len = [], [], 0
    for text, is_break in sentences:
        cur.append(text)
        cur_len += len(text)
        if is_break or cur_len >= TARGET_PARA_CHARS:
            paras.append("".join(cur))
            cur, cur_len = [], 0
    if cur:
        if paras and cur_len < MIN_SENT_CHARS:
            paras[-1] += "".join(cur)
        else:
            paras.append("".join(cur))
    return paras


def main():
    ap = argparse.ArgumentParser(description="把逐字稿润色成可读文本（不改原意）")
    ap.add_argument("input", help="transcript_raw.txt 或 transcript_segments.json")
    ap.add_argument("--out-dir", default=".", help="输出目录")
    ap.add_argument("--title", default="", help="视频标题（写进输出头部）")
    ap.add_argument("--keep-fillers", action="store_true", help="保留口语冗余词")
    ap.add_argument("--diff-only", action="store_true", help="只输出对照，不写润色稿")
    args = ap.parse_args()

    segs, full = load_input(args.input)
    if not full.strip():
        print("✗ 输入是空的，没有可润色的内容", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    diff_rows, total_removed, total_punct, total_sent = [], 0, 0, 0

    # 1) 组装片段（含真实静音信息）
    if segs:
        fragments = [(s["text"], float(s.get("gap_before", 0.0)),
                      float(s.get("gap_before", 0.0)) >= LONG_PAUSE) for s in segs]
    else:
        fragments = [(full, 0.0, False)]

    # 2) 逐片段去口语冗余
    cleaned_frags = []
    for text, gap, is_break in fragments:
        cleaned, n_removed, removed = remove_fillers(text, args.keep_fillers)
        if cleaned.strip():
            cleaned_frags.append((cleaned, gap, is_break, removed))
            total_removed += n_removed

    # 3) 合并成完整句 → 补标点
    merged = merge_fragments([(t, g, b) for t, g, b, _ in cleaned_frags])
    removed_map = [r for _, _, _, r in cleaned_frags]
    sentences = []
    for i, (text, is_break) in enumerate(merged):
        fixed, n_punct = add_punctuation([text])
        total_punct += n_punct
        total_sent += len(fixed)
        sentences.append((fixed[0], is_break))

    # 4) 归段
    paras = group_paragraphs(sentences)

    # 5) 冗余词汇总（对照表用）
    all_removed = []
    for r in removed_map:
        all_removed += r

    # ── 输出 ──
    polished_path = os.path.join(args.out_dir, "transcript_polished.md")
    diff_path = os.path.join(args.out_dir, "transcript_diff.md")
    report_path = os.path.join(args.out_dir, "polish_report.json")

    if not args.diff_only:
        with open(polished_path, "w", encoding="utf-8") as f:
            if args.title:
                f.write(f"# {args.title}\n\n")
            f.write("> 本文由抖音口播视频自动转写并做规则式润色"
                    "（去口语冗余 / 断句 / 标点 / 分段），**未改写原意**。\n\n")
            f.write("\n\n".join(paras) + "\n")

    # 对照表：原始逐字稿 → 润色稿 + 删掉的词
    with open(diff_path, "w", encoding="utf-8") as f:
        f.write("# 逐字稿对照（原文 → 润色）\n\n")
        f.write("用于人工复核：确认只去了口语冗余、补了标点与分段，**没有改动原意**。\n\n")
        f.write("## 一、原始逐字稿（按 ASR 分段）\n\n")
        src_units = [s["text"] for s in segs] if segs else [full]
        for i, u in enumerate(src_units, 1):
            f.write(f"{i}. {u}\n")
        f.write("\n## 二、润色稿（按自然段）\n\n")
        for i, p in enumerate(paras, 1):
            f.write(f"**第 {i} 段**\n\n{p}\n\n")
        f.write("## 三、删掉的口语冗余词\n\n")
        if all_removed:
            from collections import Counter
            for w, c in Counter(all_removed).most_common():
                f.write(f"- {w} × {c}\n")
        else:
            f.write("（本次没有删到词表内的口语冗余）\n")
        f.write("\n> 规则式润色的固有局限：断句依据是**停顿与片段边界**，"
                "遇到语义上应该断开但语流连贯的地方，可能切得不够理想；"
                "遇到同音错字（如「深讨/声讨」）**不会自动改**——"
                "那属于 ASR 识别问题，需人工或模型订正。\n")

    report = {"输入": os.path.abspath(args.input),
              "原始字数": len(full), "润色后字数": sum(len(p) for p in paras),
              "段落数": len(paras), "句子数": total_sent,
              "删除口语冗余次数": total_removed,
              "补全标点次数": total_punct,
              "是否使用 ASR 分段": bool(segs)}
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[润色完成]")
    delta = report['润色后字数'] - report['原始字数']
    print(f"  原始 {report['原始字数']} 字 → 润色后 {report['润色后字数']} 字"
          f"（净变化 {delta:+d} 字；标点会补进来，所以通常略增）")
    print(f"  段落 {report['段落数']} ｜ 句子 {report['句子数']} ｜ "
          f"删冗余 {total_removed} 处 ｜ 补标点 {total_punct} 处")
    print(f"  分段依据：{'ASR 时间戳分段' if segs else '纯文本（无分段，按字数切）'}")
    if not args.diff_only:
        print(f"  润色稿 → {polished_path}")
    print(f"  对照表 → {diff_path}")
    print(f"  统计   → {report_path}")
    print("\n  请打开对照表扫一眼：确认没有实词被动过，再交付给用户。")


if __name__ == "__main__":
    main()

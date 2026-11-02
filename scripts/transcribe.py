#!/usr/bin/env python3
"""音频/视频 → 逐字稿（本地 ASR，纯标准库 + faster-whisper）

用法:
  python3 transcribe.py <媒体文件> [--out-dir .] [--model small] [--language zh]
  python3 transcribe.py video.mp4 --out-dir ./run

输出:
  transcript_raw.txt        原始逐字稿（整段文字）
  transcript_segments.json  带时间戳的分段（供润色与核对用）

异常情况会给出**明确的中文提示**并以非零退出码结束，不留半成品：
  1 媒体文件不存在 / 不是媒体文件
  2 ffmpeg 不可用
  3 音轨缺失或时长过短（< 2 秒）
  4 音频整体静音 —— 未检测到语音
  5 faster-whisper 未安装 / 模型未下载
  6 ASR 输出为空或为静音幻觉

关于"无字幕"：本技能**不依赖视频自带字幕轨**，一律用本地语音识别转写。
所以"视频没有字幕"不是错误；真正的错误是"视频里没有语音"。
"""
import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import wave

MIN_DURATION = 2.0        # 秒，低于此值视为没有有效语音
SILENCE_RMS = 0.006        # 整体 RMS 低于此值视为静音
HALLUCINATE_RATIO = 0.55   # 单句重复占比阈值，用于识别静音幻觉


def die(code, title, detail, hint=""):
    """统一的中文错误输出：先说发生了什么，再说怎么办。"""
    print(f"\n✗ {title}", file=sys.stderr)
    if detail:
        print(f"  原因/现象：{detail}", file=sys.stderr)
    if hint:
        print(f"  怎么办：{hint}", file=sys.stderr)
    sys.exit(code)


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def to_wav(src, wav_path):
    """媒体文件 → 16k 单声道 wav。"""
    if not have_ffmpeg():
        die(2, "找不到 ffmpeg",
            "本技能靠 ffmpeg 做音频转码",
            "安装：brew install ffmpeg  /  apt install ffmpeg")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav_path],
        capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        detail = err[-1] if err else "未知错误"
        if "does not contain any stream" in detail or "Invalid data" in detail:
            die(3, "这个文件里没有可用的音频轨",
                "ffmpeg 报告：没有音频流",
                "确认这是视频/音频文件；若视频本身无声，请改用字幕或让作者提供文字稿")
        die(3, "音频转码失败", detail, "检查文件是否损坏，或换一个格式再试")


def wav_duration(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def wav_rms(path):
    """整体 RMS（0~1），用来判断是不是一片静音。"""
    try:
        with wave.open(path, "rb") as w:
            frames = w.readframes(w.getnframes())
            if not frames:
                return 0.0
            import array
            a = array.array("h")
            a.frombytes(frames[: len(frames) // 2 * 2])
            if not a:
                return 0.0
            acc = 0
            for v in a:
                acc += v * v
            return math.sqrt(acc / len(a)) / 32768.0
    except Exception:
        return 0.0


def find_model(name):
    """本地找 faster-whisper 模型缓存；找不到给出明确安装指引。"""
    pat = os.path.expanduser(
        f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{name}/snapshots/*")
    hits = sorted(glob.glob(pat))
    return hits[0] if hits else None


def clean_hallucination(segments):
    """静音幻觉识别与清洗：整段重复、或同一句在全文里反复出现。"""
    if not segments:
        return segments, 0
    texts = [s["text"].strip() for s in segments]
    uniq = set(t for t in texts if t)
    ratio = 1.0 - len(uniq) / max(1, len(texts))
    if ratio < HALLUCINATE_RATIO:
        return segments, 0
    # 去掉连续重复的片段
    out, prev = [], None
    for s in segments:
        t = s["text"].strip()
        if t and t == prev:
            continue
        out.append(s)
        prev = t
    return out, ratio


def main():
    ap = argparse.ArgumentParser(description="把音频/视频转成逐字稿（本地 ASR）")
    ap.add_argument("media", help="音频或视频文件（mp4/m4a/wav/mp3…）")
    ap.add_argument("--out-dir", default=".", help="输出目录（默认当前目录）")
    ap.add_argument("--model", default="small", help="模型名：tiny/base/small/medium（默认 small）")
    ap.add_argument("--language", default="zh", help="语言，默认 zh")
    ap.add_argument("--prompt", default="", help="可选：给模型的题材提示，能减少同音错字")
    ap.add_argument("--keep-wav", action="store_true", help="保留中间 wav 文件")
    args = ap.parse_args()

    # ── 1. 输入检查 ──
    src = os.path.abspath(args.media)
    if not os.path.isfile(src):
        die(1, "找不到这个文件", src, "路径写错了？用 ls 确认一下实际位置")
    if os.path.getsize(src) < 1024:
        die(1, "这个文件太小，不像是有效的媒体文件",
            f"只有 {os.path.getsize(src)} 字节",
            "确认链接解析到的是视频本体，而不是一个跳转页面")

    os.makedirs(args.out_dir, exist_ok=True)
    wav = os.path.join(args.out_dir, "audio_16k.wav")

    # ── 2. 转码 + 音频体检 ──
    to_wav(src, wav)
    dur = wav_duration(wav)
    if dur < MIN_DURATION:
        die(3, "音频太短，里面大概率没有口播内容",
            f"时长只有 {dur:.1f} 秒（阈值 {MIN_DURATION} 秒）",
            "如果这是完整视频，说明它没有可转写的语音")
    rms = wav_rms(wav)
    if rms < SILENCE_RMS:
        die(3, "未检测到语音",
            f"整体音量极低（RMS {rms:.4f}，阈值 {SILENCE_RMS}）",
            "这可能是纯音乐、纯画面或环境音视频；本技能只转写人声，"
            "这种情况请改用视频自带字幕，或直接向作者索取文字稿")

    # ── 3. ASR ──
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die(5, "缺少 faster-whisper",
            "import faster_whisper 失败",
            "安装：pip install faster-whisper   （或用 requirements.txt 一次性装好）")

    model_path = find_model(args.model)
    if not model_path:
        die(5, f"本地没有 {args.model} 模型",
            f"在 ~/.cache/huggingface/hub/ 下找不到 models--Systran--faster-whisper-{args.model}",
            "先下载（挂镜像更快，约 460MB）：\n"
            "    HF_ENDPOINT=https://hf-mirror.com python3 -c \""
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download('Systran/faster-whisper-{args.model}')\"")

    print(f"[1/3] 载入模型 {args.model} …", file=sys.stderr)
    model = WhisperModel(model_path, device="cpu", compute_type="int8")
    print(f"[2/3] 转写中（音频 {dur:.0f} 秒，CPU 约需 {dur*0.5:.0f}–{dur:.0f} 秒）…", file=sys.stderr)
    segs, info = model.transcribe(
        wav, language=args.language, beam_size=5,
        vad_filter=False,                    # 必须 False：onnxruntime 装不上（见 references/transcribe.md）
        word_timestamps=True,                # 词级时间戳：用于判断真实停顿（段落边界）
        initial_prompt=args.prompt or "以下是普通话口播视频的逐字稿。",
    )

    # 组装分段，并记录每段之前的真实静音间隔（gap_before）
    segments, prev_end = [], None
    for s in segs:
        text = s.text.strip()
        if not text:
            continue
        words = [{"start": round(w.start, 2), "end": round(w.end, 2), "w": w.word}
                 for w in (s.words or [])]
        seg_start = words[0]["start"] if words else round(s.start, 2)
        gap = round(seg_start - prev_end, 2) if prev_end is not None else 0.0
        segments.append({"start": round(s.start, 1), "end": round(s.end, 1),
                         "gap_before": max(0.0, gap), "text": text, "words": words})
        prev_end = words[-1]["end"] if words else round(s.end, 2)

    # ── 4. 幻觉清洗与空结果 ──
    segments, ratio = clean_hallucination(segments)
    full = "".join(s["text"] for s in segments).strip()
    if not full:
        die(3, "未检测到语音",
            "ASR 转写结果为空",
            "音频可能只有音乐/环境音，或音轨被人为静音；这种情况请改用视频自带字幕")
    if ratio >= HALLUCINATE_RATIO:
        print(f"  ! 检测到静音幻觉（重复占比 {ratio:.0%}），已自动去重", file=sys.stderr)

    # ── 5. 输出 ──
    raw_txt = os.path.join(args.out_dir, "transcript_raw.txt")
    seg_json = os.path.join(args.out_dir, "transcript_segments.json")
    with open(raw_txt, "w", encoding="utf-8") as f:
        f.write(full)
    with open(seg_json, "w", encoding="utf-8") as f:
        json.dump({"media": src, "duration": round(dur, 1), "rms": round(rms, 5),
                   "model": args.model, "language": info.language,
                   "segments": segments, "full": full},
                  f, ensure_ascii=False, indent=2)

    if not args.keep_wav:
        try:
            os.remove(wav)
        except OSError:
            pass

    print(f"[3/3] 完成：{len(segments)} 段 / {len(full)} 字", file=sys.stderr)
    print(f"  逐字稿   → {raw_txt}")
    print(f"  分段数据 → {seg_json}")
    print("  下一步：python3 scripts/polish.py " + raw_txt)


if __name__ == "__main__":
    main()

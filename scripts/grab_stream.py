#!/usr/bin/env python3
"""抖音视频流地址抓取（自包含，无需 agent-browser）

用 Playwright 驱动系统已装的 Chrome，在页面内执行 JS 拿媒体流地址。

用法:
  python3 grab_stream.py <VIDEO_ID> [--out stream_result.json] [--headless]

输出 JSON: {video_id, url, method, meta, video_duration}

前置:
  pip install playwright        # 已有则跳过
  系统需安装 Google Chrome      # 用 channel="chrome" 直接驱动，无需 playwright install 下载内核

为什么必须有浏览器:
  抖音的分享页 HTML 与开放接口都拿不到播放地址了（见 references/transcribe.md），
  只有在真实浏览器里跑 JS 才能取到。
"""
import argparse
import json
import os
import sys
import time

# 从 performance 里挖纯音频流（体积小，下载转码快）
JS_PERF = """
() => performance.getEntriesByType('resource').map(e => e.name)
        .filter(n => /media-audio-und-mp4a/.test(n)).pop() || ''
"""
JS_CURRENTSRC = "() => { const v = document.querySelector('video'); return v ? v.currentSrc : ''; }"
JS_HTMLSCAN = """
() => {
  const s = new Set();
  (document.documentElement.innerHTML.match(/https:[^"'\\s]*douyinvod[^"'\\s]*/g) || [])
    .forEach(u => s.add(u.replace(/&amp;/g, '&')));
  return Array.from(s).join('\\n');
}
"""
JS_META = """
() => Array.from(document.querySelectorAll('meta'))
    .filter(m => /description|title/i.test(m.getAttribute('name') || m.getAttribute('property') || ''))
    .map(m => ((m.getAttribute('name') || m.getAttribute('property')) + ' = ' + (m.getAttribute('content') || '')))
    .join('\\n')
"""
JS_PLAY = """
() => { const v = document.querySelector('video');
        if (v) { v.muted = true; v.play(); return 'playing dur=' + v.duration; }
        return 'no-video'; }
"""


def main():
    ap = argparse.ArgumentParser(description="Grab Douyin media stream URL via Playwright.")
    ap.add_argument("video_id", help="抖音视频 ID（数字）")
    ap.add_argument("--out", default="stream_result.json")
    ap.add_argument("--headless", action="store_true", help="默认 headed，headless 更易被风控")
    ap.add_argument("--wait", type=int, default=9, help="播放后等待资源进 performance 的秒数")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("缺少 playwright：pip install playwright（并确保系统装了 Google Chrome）")

    url_page = f"https://www.douyin.com/video/{args.video_id}"
    result = {"video_id": args.video_id, "url": "", "method": "", "meta": "", "video_duration": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=args.headless,
            args=["--autoplay-policy=no-user-gesture-required",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        try:
            page.goto(url_page, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
            try:
                page.evaluate(JS_PLAY)
            except Exception as e:
                print(f"[warn] 播放触发失败: {e}", file=sys.stderr)
            time.sleep(args.wait)

            result["meta"] = page.evaluate(JS_META)
            try:
                result["video_duration"] = page.evaluate(
                    "() => { const v = document.querySelector('video'); return v ? v.duration : null; }")
            except Exception:
                pass

            # 三条路并列，谁先命中用谁（2026-11-02 实测：performance 未命中、currentSrc 命中）
            u = (page.evaluate(JS_PERF) or "").strip()
            if u:
                result["url"], result["method"] = u, "performance/media-audio-und-mp4a"

            if not result["url"]:
                u = (page.evaluate(JS_CURRENTSRC) or "").strip()
                if u and not u.startswith("blob:"):
                    result["url"], result["method"] = u, "video.currentSrc"

            if not result["url"]:
                blob = page.evaluate(JS_HTMLSCAN) or ""
                cands = [x for x in blob.split("\n") if x.strip()]
                if cands:
                    result["url"], result["method"] = cands[-1], "html-scan-douyinvod"

            if not result["url"]:
                result["url"] = (page.evaluate(JS_CURRENTSRC) or "").strip()
                result["method"] = "currentSrc-blob-or-empty"
        finally:
            ctx.close()
            browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if not result["url"] or result["url"].startswith("blob:"):
        print("\n[!] 未取到可下载直链（可能走 MSE）。换 --headless 关闭再试，或改用下方 HTML 直链兜底。",
              file=sys.stderr)


if __name__ == "__main__":
    main()

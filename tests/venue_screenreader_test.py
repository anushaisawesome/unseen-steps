"""Automated test of the venue page (web/listen.html) as a screen-reader user on a phone, recorded as a video.

    python scripts/web_sync_server.py && python scripts/dev_server.py &      # the site with its live functions
    python tests/venue_screenreader_test.py --y4m dancer.y4m --out run/      # a .y4m clip stands in for the camera

A phone-sized Chromium (iPhone 14 viewport) gets a fake camera playing the clip. The run uses the keyboard only:
Tab from the top through the skip link, nav and settings, turn on "Also send lines to my screen reader", Start
listening with Enter, wait while narration arrives, then Stop. An overlay injected by this test (not part of the
site) shows what a screen reader would announce, computed from the accessibility tree: each focus change as
"role, name, state" and every change to a live region (role="status" and the aria-live narration), newest first.
It is a simulation from the accessibility tree, not VoiceOver or TalkBack. axe-core checks WCAG 2.2 AA first.
Writes video.webm, announcements.txt and requests.txt (each /api/describe call with its time) to --out.
"""
import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PANEL = r"""
(() => {
  if (window.__sr) return;
  const log = [];
  window.__sr = log;
  const t0 = performance.now();
  const panel = document.createElement('div');
  panel.id = 'sr-panel';
  panel.setAttribute('aria-hidden', 'true');
  panel.style.cssText = 'position:fixed;left:0;right:0;bottom:0;height:34vh;z-index:99999;background:#0e1424;color:#f3ede2;' +
    'font:15px/1.35 -apple-system,system-ui,sans-serif;padding:10px 12px;overflow:hidden;border-top:3px solid #ff48b0;box-sizing:border-box';
  panel.innerHTML = '<div style="font-weight:700;color:#ff6cc0;font-size:13px;margin-bottom:6px">Screen reader output (simulated from the accessibility tree, automated test)</div><ol id="sr-list" style="list-style:none;margin:0;padding:0"></ol>';
  const add = (kind, text) => {
    text = (text || '').replace(/\s+/g, ' ').trim();
    if (!text) return;
    const s = ((performance.now() - t0) / 1000).toFixed(1);
    log.push({t: +s, kind, text});
    const li = document.createElement('li');
    li.style.cssText = 'padding:5px 0;border-bottom:1px solid #2a3350';
    const tag = kind === 'focus' ? '#9db4e6' : kind === 'axe' ? '#7cd38f' : '#ff9ad3';
    li.innerHTML = `<span style="color:${tag};font-weight:700;font-size:12px">${s}s ${kind === 'focus' ? 'FOCUS' : kind === 'axe' ? 'CHECK' : 'ANNOUNCED'}</span><br>`;
    li.appendChild(document.createTextNode(text));
    const list = document.getElementById('sr-list');
    list.insertBefore(li, list.firstChild);
    while (list.children.length > 9) list.lastChild.remove();
  };
  window.__srAdd = add;
  const implicit = el => {
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'button' || (tag === 'input' && ['submit', 'button'].includes(type))) return 'button';
    if (tag === 'input' && type === 'checkbox') return 'checkbox';
    if (tag === 'input' && type === 'radio') return 'radio button';
    if (tag === 'input' && type === 'range') return 'slider';
    if (tag === 'select') return 'pop-up button';
    if (tag === 'input' || tag === 'textarea') return 'text field';
    if (/^h[1-6]$/.test(tag)) return 'heading level ' + tag[1];
    return tag;
  };
  const nameOf = el => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.getAttribute('aria-labelledby')) return el.getAttribute('aria-labelledby').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
    if (el.labels && el.labels.length) return [...el.labels].map(l => l.textContent).join(' ');
    return el.textContent || el.value || '';
  };
  const stateOf = el => {
    const s = [];
    if (el.type === 'checkbox' || el.type === 'radio') s.push(el.checked ? (el.type === 'radio' ? 'selected' : 'checked') : (el.type === 'radio' ? 'not selected' : 'not checked'));
    if (el.tagName === 'SELECT') s.push(el.options[el.selectedIndex]?.text || '');
    if (el.type === 'range') s.push(el.getAttribute('aria-valuetext') || el.value);
    if (el.getAttribute('aria-current')) s.push('current page');
    if (el.getAttribute('aria-pressed')) s.push(el.getAttribute('aria-pressed') === 'true' ? 'pressed' : 'not pressed');
    const d = el.getAttribute('aria-describedby');
    if (d) s.push(document.getElementById(d)?.textContent || '');
    return s.filter(Boolean);
  };
  document.addEventListener('focusin', e => {
    const el = e.target;
    add('focus', [el.getAttribute('role') || implicit(el), nameOf(el), ...stateOf(el)].join(', '));
  });
  document.addEventListener('change', e => {
    const el = e.target;
    if (el.type === 'checkbox' || el.type === 'radio' || el.tagName === 'SELECT') add('focus', [nameOf(el), ...stateOf(el)].join(', '));
  });
  const watch = () => document.querySelectorAll('[aria-live],[role="status"],[role="alert"]').forEach(region => {
    if (region.__watched || region.closest('#sr-panel')) return;
    region.__watched = true;
    new MutationObserver(() => add('announce', region.textContent)).observe(region, {childList: true, characterData: true, subtree: true});
  });
  const start = () => { document.body.appendChild(panel); watch(); new MutationObserver(watch).observe(document.body, {childList: true, subtree: true}); };
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8800/listen")
    ap.add_argument("--y4m", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=int, default=45, help="how long to listen")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    requests = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={args.y4m}",
                                          "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"])
        device = dict(p.devices["iPhone 14"])
        device.pop("default_browser_type", None)
        ctx = browser.new_context(**device, record_video_dir=str(out), record_video_size=device["viewport"],
                                  permissions=["camera"])
        ctx.add_init_script(PANEL)
        page = ctx.new_page()
        t_start = time.time()
        started = {}
        page.on("request", lambda r: started.__setitem__(r, time.time()) if "/api/describe" in r.url else None)

        def done(r):
            if "/api/describe" in r.url:
                try:
                    line = r.json().get("line")
                except Exception:
                    line = None
                requests.append({"at": round(started.get(r.request, time.time()) - t_start, 1),
                                 "seconds": round(time.time() - started.get(r.request, time.time()), 2), "status": r.status, "line": line})
        page.on("response", done)
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(800)
        # axe-core, WCAG 2.2 AA, without the test's own overlay
        page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js")
        result = page.evaluate("""async () => { const r = await axe.run({exclude: [['#sr-panel']]},
            {runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}); return r.violations.map(v => v.id + ' x' + v.nodes.length); }""")
        page.evaluate("v => window.__srAdd('axe', v.length ? 'axe: ' + v.join(', ') : 'axe: 0 WCAG 2.2 AA violations on this page')", result)
        page.wait_for_timeout(1500)
        # Keyboard only, from the top, like a screen-reader user
        for _ in range(40):
            page.keyboard.press("Tab")
            page.wait_for_timeout(650)
            focused = page.evaluate("document.activeElement && document.activeElement.id")
            if focused == "announce" and not page.is_checked("#announce"):
                page.keyboard.press("Space")
                page.wait_for_timeout(700)
            if focused == "start":
                break
        page.wait_for_timeout(800)
        page.keyboard.press("Enter")
        # keep the camera and the spoken line in view for whoever watches the recording
        page.wait_for_timeout(2500)
        page.evaluate("document.getElementById('stage')?.scrollIntoView({block: 'start'})")
        page.wait_for_timeout(args.seconds * 1000)
        page.evaluate("document.getElementById('start').scrollIntoView({block: 'center'})")
        page.focus("#start")
        page.wait_for_timeout(800)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)
        log = page.evaluate("window.__sr")
        video = page.video.path()
        ctx.close()
        browser.close()
    Path(video).rename(out / "video.webm")
    (out / "announcements.txt").write_text("\n".join(f"{e['t']:>6.1f}s  {e['kind']:<8} {e['text']}" for e in log) + "\n")
    (out / "requests.txt").write_text("\n".join(json.dumps(r) for r in requests) + "\n")
    print(f"axe: {result or 'no violations'}; {sum(1 for e in log if e['kind'] == 'announce')} announcements; "
          f"{len(requests)} describe calls, {sum(1 for r in requests if r['line'])} with a line")


if __name__ == "__main__":
    main()

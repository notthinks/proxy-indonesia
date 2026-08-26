#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_all.py — Kumpulkan proxy dari BANYAK provider sumber, dedupe, simpan.
Output: raw_proxies.txt (semua), dan lanjut ke filter Indonesia lewat geo_verify.
"""
import argparse
import json
import re
import shutil
import subprocess
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

NODE_ADAPTER = r"""
const exprs = JSON.parse(process.argv[1]);
const out = exprs.map(e => {
  try { return String(eval(e)); } catch (x) { return 'ERR:' + x.message; }
});
console.log(JSON.stringify(out));
"""


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_proxynova(html):
    """Deobfuscate IP dari HTML proxynova lewat node eval."""
    if not shutil.which("node"):
        return []
    tb = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not tb:
        return []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tb.group(1), re.S)
    items = []
    for r in rows:
        sm = re.search(r"document\.write\((.*?)\)</script>", r, re.S)
        if not sm:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        port = None
        for td in tds[1:3]:
            t = re.sub(r"<[^>]+>", "", td).strip()
            if re.fullmatch(r"\d{1,5}", t):
                port = int(t)
                break
        items.append({"js": sm.group(1).strip(), "port": port})
    if not items:
        return []
    payload = json.dumps([it["js"] for it in items])
    res = subprocess.run(["node", "-e", NODE_ADAPTER, payload],
                         capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        return []
    try:
        ips = json.loads(res.stdout)
    except Exception:
        return []
    out = []
    for it, ip in zip(items, ips):
        ip = ip.strip()
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
            if all(0 <= int(o) <= 255 for o in ip.split(".")) and it["port"]:
                out.append(f"{ip}:{it['port']}")
    return out


def parse_lines(text, scheme_hint):
    """Parse format text generik: baris ip:port^ atau scheme://ip:port."""
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # buang whitespace/garbage
        if "://" in line:
            rest = line.split("://", 1)[1]
        else:
            rest = line
        # ambil ip:port di awal (ada kemungkinan ada suffix seperti country tag)
        m = re.match(r"(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))", rest)
        if m:
            ip, port = m.group(1), m.group(2)
            if 1 <= int(port) <= 65535 and all(0 <= int(o) <= 255 for o in ip.split(".")):
                out.add(f"{ip}:{port}")
    return out


def main():
    p = argparse.ArgumentParser(description="Kumpulkan proxy dari banyak provider")
    p.add_argument("--providers", default="providers.json")
    p.add_argument("--out", default="raw_proxies.txt")
    p.add_argument("--per-html", action="store_true", help="parse proxynova juga")
    a = p.parse_args()

    cfg = json.load(open(a.providers))
    all_proxies = set()
    stats = {}

    for pr in cfg["providers"]:
        name, url = pr["name"], pr["url"]
        try:
            text = fetch(url)
        except Exception as e:
            stats[name] = f"ERR {type(e).__name__}"
            print(f"[{name}] gagal: {type(e).__name__}")
            continue
        if pr["format"] == "html_js_obfuscated":
            parsed = set(parse_proxynova(text))
        else:
            parsed = parse_lines(text, pr.get("scheme", "http"))
        all_proxies |= parsed
        stats[name] = f"{len(parsed)}"
        print(f"[{name}] {len(parsed)} proxy diparse")

    all_proxies = sorted(all_proxies)
    with open(a.out, "w") as f:
        f.write("\n".join(all_proxies) + "\n")
    print(f"\n=== TOTAL UNIK: {len(all_proxies)} proxy -> {a.out} ===")


if __name__ == "__main__":
    main()
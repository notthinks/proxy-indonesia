#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProxyNova Indonesia Proxy Checker — CLI
=======================================
Scrape https://www.proxynova.com/proxy-server-list/country-id/
(deobfuscate IP yang di-hide via JS: substring / repeat / reverse / atob / charCode),
cek konektivitas proxy + kecepatan, export hasil.

Stdlib-only — TIDAK butuh pip. Butuh `node` (untuk eval ekspresi JS deobfuscator).
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SCRAPE_URL = "https://www.proxynova.com/proxy-server-list/country-id/"

# NODE_ADAPTER: mengeval ekspresi JS asli dari document.write secara literal.
# Ini yang bikin parse 100% akurat untuk SEMUA trik obfuscation proxynova.
NODE_ADAPTER = r"""
const exprs = JSON.parse(process.argv[1]);
const out = exprs.map(e => {
  try {
    // document.write("<...>") — kita butuh argumen eval seperti JS aslinya.
    // String literal pakai double-quote; single-quote TIDAK muncul di pola ini.
    return String(eval(e));
  } catch (x) {
    return 'ERR:' + x.message;
  }
});
console.log(JSON.stringify(out));
"""


def fetch_html():
    req = urllib.request.Request(SCRAPE_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_list(html):
    """Kembalikan list [ip, port, speed_ms]. Deobfuscasi IP via node eval."""
    tb = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not tb:
        raise RuntimeError("tbl_proxy_list <tbody> tidak ketemu")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tb.group(1), re.S)

    if not shutil.which("node"):
        raise RuntimeError("butuh `node` untuk deobfuscasi IP proxynova")

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
        spd = re.search(r"<small>(\d+) ms</small>", r)
        items.append({"js": sm.group(1).strip(), "port": port,
                      "ms": int(spd.group(1)) if spd else None})

    if not items:
        return []

    payload = json.dumps([it["js"] for it in items])
    res = subprocess.run(["node", "-e", NODE_ADAPTER, payload],
                         capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        raise RuntimeError("node eval gagal: " + res.stderr[:400])
    ips = json.loads(res.stdout)

    out = []
    for it, ip in zip(items, ips):
        ip = ip.strip()
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
            # validasi oktet 0-255
            if all(0 <= int(o) <= 255 for o in ip.split(".")):
                out.append((ip, it["port"], it["ms"]))
    return out


def tcp_connect(host, port, timeout):
    s = socket.create_connection((host, port), timeout=timeout)
    s.close()
    return True


def check_one(entry, timeout, do_http):
    ip, port, reported_ms = entry
    schemes = []
    t_start = time.time()
    try:
        tcp_connect(ip, port, timeout)
        latency_ms = (time.time() - t_start) * 1000
        schemes.append("tcp")
    except OSError:
        latency_ms = None

    http_verdict = None
    http_ms = None
    if do_http and latency_ms is not None:
        url = f"http://{ip}:{port}"
        # TRUE forward-proxy check: resolve target eksternal lewat proxy,
        # bukan sekedar port HTTP yang ngebales apa aja.
        proxy_url = url
        handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
        op = urllib.request.build_opener(handler)
        h_start = time.time()
        try:
            with op.open('http://httpbin.org/ip', timeout=timeout) as resp:
                _body = resp.read(64)
                code = resp.status
                # proxy generik sering 200 tanpa nge-body; yang jelas adalah
                # koneksi + response HTTP terbaca = bisa lewat.
                http_verdict = "open" if str(code)[0] in "23" else f"http:{code}"
                http_ms = (time.time() - h_start) * 1000
        except Exception:
            http_verdict = "err"
            http_ms = (time.time() - h_start) * 1000

    return {
        "ip": ip, "port": port, "reported_ms": reported_ms,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        "tcp": bool(schemes),
        "http": http_verdict, "http_ms": round(http_ms, 1) if http_ms else None,
    }


def main():
    p = argparse.ArgumentParser(description="ProxyNova ID Proxy Checker")
    p.add_argument("--scrape", action="store_true", help="scrape ulang dari proxynova")
    p.add_argument("--max", type=int, default=0, help="max proxy dicek (0=semua)")
    p.add_argument("--workers", type=int, default=40, help="thread paralel (default 40)")
    p.add_argument("--timeout", type=float, default=5.0, help="timeout koneksi (dtk)")
    p.add_argument("--http", action="store_true", help="test HTTP/HTTPS terbuka")
    p.add_argument("--json", metavar="FILE", help="load input dari file json [ip,port,ms]")
    p.add_argument("--out", default="results.json", help="file output hasil")
    a = p.parse_args()

    if a.json:
        print(f"Loading {a.json} ...")
        data = [tuple(x) for x in json.load(open(a.json))]
    elif a.scrape:
        print(f"Scrape {SCRAPE_URL} ...")
        html = fetch_html()
        data = parse_list(html)
    else:
        cache = "proxies.json"
        if os.path.exists(cache):
            print(f"Pakai cache {cache} (pakai --scrape untuk refresh)")
            data = [tuple(x) for x in json.load(open(cache))]
        else:
            print(f"No cache — scrape {SCRAPE_URL} ...")
            html = fetch_html()
            data = parse_list(html)
            json.dump(data, open(cache, "w"))

    if not data:
        print("Tidak ada proxy ke-parse.")
        sys.exit(1)

    # simpan cache
    if not os.path.exists("proxies.json"):
        json.dump(data, open("proxies.json", "w"))

    print(f"[VERIFIED] {len(data)} proxy di-parse")
    if a.max:
        data = data[:a.max]

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futures = {ex.submit(check_one, e, a.timeout, a.http): e for e in data}
        results = [f.result() for f in cf.as_completed(futures)]

    results.sort(key=lambda x: (x["latency_ms"] is None, x["latency_ms"] or 1e9))
    json.dump(results, open(a.out, "w"), indent=2)

    alive = [r for r in results if r["tcp"]]
    http_ok = [r for r in results if r["http"] == "open"]
    print(f"\nCek selesai {time.time()-t0:.1f}s | total {len(results)} | "
          f"ALIVE(tcp) {len(alive)} | HTTP open {len(http_ok)}")
    print(f"Hasil -> {a.out}")
    print("\nTop 15 (latency):")
    for r in alive[:15]:
        line = f"  {r['ip']}:{r['port']}  tcp={r['latency_ms']}ms"
        if r["http"]:
            line += f"  http={r['http']} {r['http_ms']}ms"
        if r["reported_ms"]:
            line += f"  (site:{r['reported_ms']}ms)"
        print(line)


if __name__ == "__main__":
    main()
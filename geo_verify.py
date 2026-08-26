#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
geo_verify.py — Filter proxy INDONESIA yang aktif.

Verifikasi DUA lapis per proxy candidate:
  1) GEO: request via proxy ke ip-api.com => countryCode == "ID"
  2) FORWARD: proxy harus bisa buka situs eksternal (example.com -> 2xx)
Yang LOLOS KEDUA = proxy Indonesia sungguhan & bisa dipakai internet.

Paralel tinggi. Output: indonesia_proxies.txt (aktif) + log.
"""
import argparse
import concurrent.futures as cf
import json
import subprocess
import sys

GEO_URL = "http://ip-api.com/json/?fields=status,countryCode,query"
FWD_URL = "http://example.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def curl(proxy, url, timeout=8):
    """Return stdout or None."""
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-A", UA,
             "-x", f"http://{proxy}", url],
            capture_output=True, text=True, timeout=timeout + 2)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def verify_one(proxy):
    """Return (proxy, exit_ip, fwd_ok) atau None jika bukan Indonesia aktif."""
    geo_raw = curl(proxy, GEO_URL)
    if not geo_raw:
        return None
    try:
        geo = json.loads(geo_raw)
    except Exception:
        return None
    if geo.get("status") != "success" or geo.get("countryCode") != "ID":
        return None
    # Lapis 2: forward ke situs eksternal harus jalan
    fwd_code = None
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", str(8), "-x", f"http://{proxy}", FWD_URL],
            capture_output=True, text=True, timeout=10)
        fwd_code = out.stdout.strip()
    except Exception:
        fwd_code = None
    if not fwd_code or not fwd_code.startswith("2"):
        return None
    return (proxy, geo.get("query"), fwd_code)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", default="raw_proxies.txt")
    p.add_argument("--out", default="indonesia_proxies.txt")
    p.add_argument("--workers", type=int, default=60)
    p.add_argument("--max", type=int, default=0, help="maks proxy diproses")
    a = p.parse_args()

    with open(a.inp) as f:
        proxies = [l.strip() for l in f if l.strip()]
    if a.max:
        proxies = proxies[:a.max]
    print(f"Memproses {len(proxies)} proxy candidate ...")

    hits = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(verify_one, proxies):
            if res:
                hits.append(res)
                print(f"  OK  {res[0]}  exit_ip={res[1]}  fwd={res[2]}")

    # dedupe by exit_ip (beberapa proxy bisa share exit)
    seen = set()
    uniq = []
    for proxy, exit_ip, fwd in sorted(hits, key=lambda x: x[0]):
        key = exit_ip or proxy
        if key not in seen:
            seen.add(key)
            uniq.append(proxy)
    uniq.sort()

    with open(a.out, "w") as f:
        for pr in uniq:
            f.write(pr + "\n")
    print(f"\n=== [VERIFIED] {len(uniq)} proxy INDONESIA aktif -> {a.out} ===")
    for pr in uniq:
        print("  " + pr)


if __name__ == "__main__":
    main()
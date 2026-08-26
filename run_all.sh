#!/usr/bin/env bash
# Orchestrator: scrape semua provider -> filter proxy Indonesia aktif
set -e
cd "$(dirname "$0")"

echo "== [1/3] Scrape dari semua provider =="
python3 scrape_all.py

echo "== [2/3] Filter proxy Indonesia aktif (geo + forward verify) =="
python3 geo_verify.py --workers 80

echo "== [3/3] Selesai =="
echo "Hasil: indonesia_proxies.txt"
wc -l < indonesia_proxies.txt | xargs echo "Jumlah proxy aktif:"
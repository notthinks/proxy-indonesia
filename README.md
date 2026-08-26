# 🌏 Proxy Indonesia Auto-Scanner

Auto-scan otomatis proxy **Indonesia aktif** dari banyak provider sumber, verifikasi geo + forward, dan publikasikan daftar proxy live.

## 🚀 Fitur

- **Multi-provider**: kumpulin proxy dari 9+ sumber (TheSpeedX, proxifly, shiftytr, vakhov, clarketm, monosans, hookzof, roosterkid, proxynova)
- **Geo-verified**: cuma proxy yang **terbukti keluar dari IP Indonesia** (via ip-api.com `countryCode=ID`) yang di-list
- **Forward-check**: proxy harus benar-benar bisa buka situs web eksternal (bukan cuma port terbuka) — filter proxy "setengah jalan"
- **Auto-update**: GitHub Actions jalan terjadwal (setiap 6 jam) → refresh `indonesia_proxies.txt` otomatis
- **Paralel tinggi**: verifikasi ribuan proxy dalam hitungan menit

## 📁 Struktur

```
.
├── providers.json          # daftar sumber proxy (tambah bebas)
├── scrape_all.py           # kumpulin dari semua provider, dedupe
├── geo_verify.py           # filter proxy Indonesia aktif (2 lapis verifikasi)
├── run_all.sh              # orchestrator: scrape → verify
├── tools/pn_checker.py     # (opsional) single-source proxynova checker CLI
└── indonesia_proxies.txt   # ⭐ HASIL: daftar proxy Indonesia aktif
```

## 🧰 Cara Pakai Lokal

```bash
# 1. Kumpulin dari semua provider
python3 scrape_all.py

# 2. Filter proxy Indonesia aktif (butuh `curl`, `node`)
python3 geo_verify.py --workers 80

# 3. Lihat hasil
cat indonesia_proxies.txt
```

Butuh: `python3`, `curl`, `node`.

## ⚙️ Verifikasi yang Dijalankan

Untuk setiap proxy candidate, **dua lapis**:

1. **Geo-check** — request lewat proxy ke `ip-api.com`, pastikan `countryCode == "ID"`
2. **Forward-check** — proxy harus bisa buka `example.com` dan dapat HTTP `2xx`

Hanya yang lolos **keduanya** yang masuk. No gatekeeping, semua di-verifikasi hidup.

## 📅 Auto-scan

GitHub Actions `.github/workflows/scan.yml` jalan **setiap 30 menit** (dan manual via `workflow_dispatch`) — auto scrape, auto verify, auto commit hasil terbaru ke `indonesia_proxies.txt`.

> ⚠️ Proxy publik itu **berumur pendek** — selalu pakai versi terbaru dari `indonesia_proxies.txt`.
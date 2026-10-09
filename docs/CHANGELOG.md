# GONKAFARM — Riwayat Versi

Satu repo, tag per versi. Lihat kode versi mana pun:
```bash
git checkout v1.0.0   # lihat / jalan versi 1.0.0
git checkout main      # kembali ke terbaru
```

## v1.0.0 — 2026-10-10
**Optimasi: paralelisasi mail + proxy residensial per-request**

| Item | Sebelum | Sesudah |
|------|---------|---------|
| Mail polling | Lock global → semua worker antri 1 per 1 | MailClient per worker, lock dihapus |
| Proxy | `127.0.0.1:8888` (MITM lokal, 1 IP) | Oxylabs residensial, IP baru tiap koneksi |
| Probe 20 paralel | 5/20 ok, 36s | **20/20 ok, 7s** |
| WORKERS | 3 | 6 |

Detail teknis:
- `mail.py`: hapus `MailClient._global`, `threading` import. Session-id jadi per-thread.
- `farm.py`: `worker()` membuat MailClient sendiri; `cmd_farm`/`cmd_unlimited` tidak lagi membuat satu client bersama.
- `gonka.py`: `_opener(True)` membuat `sessid` digit acak per koneksi → Oxylabs memberi IP exit baru tiap request.
- `config.py`: `PROXY` ke Oxylabs, `WORKERS=6`.

## v0.1.0 — 2026-10-09 (commit a0d45b5)
Baseline: auto-farm GonkaRouter + sync 9router, MailClient berbagi lock, proxy 8888.

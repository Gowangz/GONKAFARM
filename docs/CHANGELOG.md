# GONKAFARM — Riwayat Versi

Dokumentasi riwayat rilis dan perubahan fitur GONKAFARM.

---

## v0.4.0 — 2026-10-31
**Fitur Utama: Proxy Manager & PetaniProxy Rotating Gateway**

- **Proxy Manager Integration** (`core/proxy_manager.py`):
  - Harvester proxy publik (HTTP, SOCKS4, SOCKS5).
  - Validasi pool via Cloudflare.
  - Rotating proxy gateway lokal.
- **PetaniProxy Forward Gateway** (`127.0.0.1:8888`):
  - Toggle `USE_PETANI_PROXY` di `config.py`.
  - Rotasi IP otomatis per request via gateway PetaniProxy.
  - Fallback otomatis ke Oxylabs residensial jika PetaniProxy nonaktif.
  - Script launcher: `scripts/start_petani.sh`.
- **Gateway Daemon Stability Fix**:
  - Perbaikan recursive call pada gateway daemon dengan target `_start_gateway`.
- **CLI & Status Enhancements**:
  - Pengecekan kesehatan gateway via `--proxy-status`.
  - Menu konfigurasi toggle mode proxy (Petani/Oxylabs).

---

## v0.3.0 — 2026-10-30
**Rotasi Proxy, Aktivasi Bonus & Sinkronisasi UUID**

- Rotasi proxy per koneksi request untuk mencegah HTTP 429 / rate limiting.
- Mekanisme aktivasi bonus akun otomatis setelah registrasi berhasil.
- Pembaruan UUID provider untuk kompatibilitas sinkronisasi terbaru.

---

## v0.2.0 — 2026-10-10
**Optimasi Paralelisasi Worker & Mail Client**

- **Mail Polling Paralel**:
  - Lock global dihapus; setiap worker menginisialisasi `MailClient` independen.
  - `session_id` dibuat per-thread.
  - Peningkatan kecepatan: probe 20 akun paralel berkurang dari 36 detik menjadi **7 detik**.
- **Skalabilitas**:
  - Peningkatan kapasitas worker default dari 3 menjadi 6 worker aktif.
- **Per-request Exit IP**:
  - `_opener(True)` menghasilkan `sessid` acak per request untuk rotasi IP residensial.

---

## v0.1.0 — 2026-10-09
**Rilis Baseline Awal**

- Otomasi registrasi akun massal GonkaRouter.
- Pengambilan OTP otomatis via worker mail.
- Ekstraksi API key dengan saldo default 20 USDT.
- Auto-sync langsung ke 9router (`http://127.0.0.1:20128`).
- Output batch terorganisir di `output/batch-N-tanggal-jumlah/`.

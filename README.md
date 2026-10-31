# GONKAFARM

[English](#english) | [Bahasa Indonesia](#bahasa-indonesia)

---

## Bahasa Indonesia

**GONKAFARM** adalah sistem otomasi farming API berperforma tinggi untuk
mendaftarkan akun GonkaRouter secara massal: ambil OTP secara otomatis dari
worker mail, verifikasi, dapatkan API key (balance 20 USDT), simpan hasilnya
ke folder per-batch, dan sinkronkan key langsung ke **9router**.

### 🆕 Fitur Terbaru (v0.4)

- **Proxy Manager Integration** — integrasi manajer proxy baru dengan harvester
  dan rotating gateway. Lihat `core/proxy_manager.py` untuk detail.
- **Gateway Daemon Fix** — perbaikan recursive call di gateway daemon;
  now menggunakan `target _start_gateway` yang stabil.
- **Proxy Rotation & UUID Update** — otomatis rotasi proxy per request dan
  update UUID provider untuk menghindari 429/rate limit.
- **Petani-Proxy Support** — gunakan `127.0.0.1:8888` dengan rotasi IP otomatis
  per request (mode favorit).

### Fitur Utama

- **Auto Farming** — jalankan `N` akun per siklus; state **auto-reset**
  setelah selesai, jadi perintah yang sama selalu = N akun baru.
- **Output per-Batch** — tiap siklus dibuat folder
  `output/batch-N-tanggal-jumlah/` berisi `apikey.txt` (1 key/baris, siap
  Bulk Add) + `accounts.txt` (akun lengkap).
- **Auto-Sync 9router** — key hasil farm langsung di-reconcile ke 9router
  (add-only, tidak pernah hapus), bisa juga manual lewat `--sync`.
- **Turnstile Solver** — otomatis menyelesaikan Cloudflare Turnstile lewat
  Waryono (header browser lengkap, cepat).
- **Proxy Support** — gunakan proxy sendiri atau **Petani-Proxy**
  (`127.0.0.1:8888`, rotating IP per request).

### 🆕 Struktur Tambahan (dari commit terbaru)

- `core/proxy_manager.py` — modul manajer proxy dengan fitur harvest,
  gateway, dan rotasi pool.
- `core/gateway.py` — perbaikan daemon gateway (_start_gateway).
- `ecosystem.config.js` — definisi app PM2 (`gonkafarm-20`).
- `docs/` — dokumentasi tambahan: `rate-limit.md`, `solver.md`, `endpoints.md`, `9router.md`.

### Struktur Proyek

- `farm.py` — orkestrasi farm, worker, output batch, reset state.
- `gonka.py` — klien API GonkaRouter (send_otp, verify, ambil key).
- `router9.py` — sinkronisasi key ke 9router.
- `mail.py` — ambil OTP dari inbox worker mail.
- `solver.py` — solver Turnstile (Waryono).
- `config.py` — konfigurasi global (proxy, worker, delay, dll).
- `ecosystem.config.js` — definisi app PM2 (`gonkafarm-20`).
- `output/` — folder arsip per-batch (tidak di-commit, berisi key/akun).

### Instalasi & Penggunaan

1. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
2. Salin `.env.example` ke `.env` dan sesuaikan:
   ```bash
   cp .env.example .env
   ```
3. Jalankan farm:
   ```bash
   python3 farm.py --accounts 20 --workers 1
   ```
4. (Opsional) via PM2 dengan banyak akun:
   ```bash
   pm2 start ecosystem.config.js   # = farm 20 akun
   ```

### Konfigurasi Pentu (`config.py`)

| Kunci | Default | Keterangan |
|---|---|---|
| `PROXY` | `http://127.0.0.1:8888` | proxy sendiri / Petani-Proxy (rotating) |
| `WORKERS` | `1` | paralel worker; naikkan = lebih cepat tapi ravan 429 |
| `DELAY_BETWEEN_ACCOUNTS` | `45` | cooldown antar akun (detik) |
| `AUTO_SYNC_9ROUTER` | `True` | sinkronkan key ke 9router otomatis |
| `AUTO_RESET_STATE` | `True` | reset state setelah siklus terbatas selesai |

### Dokumentasi

- `docs/rate-limit.md` — pengukuran ceiling, strategi 3 channel, tuning.
- `docs/solver.md` — integrasi & perbaikan Turnstile solver.
- `docs/endpoints.md` — endpoint API GonkaRouter & 9router.
- `docs/9router.md` — panduan sinkronisasi ke 9router.

### Keamanan

Data sensitif (`.env`, `Apikey.txt`, `accounts.txt`, `state.json`,
`output/`, `state_history.json`) ada di `.gitignore` — tidak akan ter-commit
ke repo publik.

### Repo Name Update

Repo ini sekarang berada di `GONKAFARM` (case uppercase) di GitHub.
Remote lama `gonkafarm` masih bisa digunakan tetapi disarankan Update ke
`GONKAFARM` untuk konsistensi.

---

## English

**GONKAFARM** is a high-performance API farming automation system for bulk
GonkaRouter account registration: automated OTP retrieval from mail worker,
verification, API key extraction (20 USDT balance), per-batch output
folders, and automatic 9router key synchronization.

### 🆕 Recent Updates (v0.4)

- **Proxy Manager Integration** — new proxy manager integration with harvester
  and rotating gateway. See `core/proxy_manager.py` for details.
- **Gateway Daemon Fix** — fix for recursive gateway daemon call; now using
  stable `target _start_gateway`.
- **Proxy Rotation & UUID Update** — automatic proxy rotation per request and
  provider UUID update to avoid 429/rate limit issues.
- **Petani-Proxy Support** — use `127.0.0.1:8888` with automatic IP rotation
  per request (preferred mode).

### Key Features

- **Auto Farming** — run `N` accounts per cycle; state **auto-resets**
  after completion, so the same command always means N fresh accounts.
- **Per-Batch Output** — each cycle creates `output/batch-N-date-count/`
  with `apikey.txt` (1 key/line, Bulk-Add ready) + `accounts.txt`.
- **Auto-Sync 9router** — farmed keys are reconciled to 9router
  (add-only), or manually via `--sync`.
- **Turnstile Solver** — auto-solves Cloudflare Turnstile via Waryono
  (full browser headers, fast).
- **Proxy Support** — use your own proxy or **Petani-Proxy**
  (`127.0.0.1:8888`, rotating IP per request).

### Project Structure

- `farm.py` — farm orchestration, workers, batch output, state reset.
- `gonka.py` — GonkaRouter API client (send_otp, verify, get key).
- `router9.py` — key sync to 9router.
- `mail.py` — OTP retrieval from mail worker inbox.
- `solver.py` — Turnstile solver (Waryono).
- `config.py` — global config (proxy, worker, delay, etc).
- `ecosystem.config.js` — PM2 app definition (`gonkafarm-20`).
- `output/` — per-batch archive folder (not committed, contains keys/accounts).

### Installation & Usage

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```
3. Farm a number of accounts:
   ```bash
   python3 farm.py --accounts 20 --workers 1
   ```
4. (Optional) via PM2:
   ```bash
   pm2 start ecosystem.config.js   # = farm 20 accounts
   ```

### Key Config (`config.py`)

| Key | Default | Description |
|---|---|---|
| `PROXY` | `http://127.0.0.1:8888` | your proxy / Petani-Proxy (rotating) |
| `WORKERS` | `1` | parallel workers; higher = faster but more 429-prone |
| `DELAY_BETWEEN_ACCOUNTS` | `45` | cooldown between accounts (seconds) |
| `AUTO_SYNC_9ROUTER` | `True` | auto sync keys to 9router |
| `AUTO_RESET_STATE` | `True` | reset state after a bounded cycle completes |

### Documentation

- `docs/rate-limit.md` — ceiling measurements, 3-channel strategy, tuning.
- `docs/solver.md` — Turnstile solver integration & fixes.
- `docs/endpoints.md` — GonkaRouter & 9router API endpoints.
- `docs/9router.md` — 9router synchronization guide.

### Security

Sensitive data (`.env`, `Apikey.txt`, `accounts.txt`, `state.json`,
`output/`, `state_history.json`) are in `.gitignore` — never committed to the
public repo.

### Repo Name Update

This repository is now at `GONKAFARM` (uppercase case) on GitHub. The old
`gonkafarm` remote can still be used but it's recommended to update to
`GONKAFARM` for consistency.

---

## License

MIT License
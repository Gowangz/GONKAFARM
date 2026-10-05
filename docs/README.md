# GONKAFARM — GonkaRouter Account Farming

Farming akun [GonkaRouter.io](https://gonkarouter.io) otomatis: daftar dengan
email temp `*@nodexdigital.web.id`, klaim bonus **20 USDT** untuk user baru,
ekstrak API key ke `Apikey.txt`, dan **auto-sync ke 9router**.

**Web**: https://gonkarouter.io/ · **Pricing**: `0.0023 / 1M Tokens`

## Status: ✅ PRODUCTION-READY

- 19 akun dalam 3 menit (mode unlimited, 2 worker) — 0 gagal
- 10/10 akun sukses dalam 242 detik (batch mode, 3 worker)
- **Auto-sync 9router** — setiap key otomatis masuk, tanpa duplikasi
- Bonus 20 USDT otomatis untuk setiap user baru
- **Tidak butuh captcha solver** — Turnstile tidak diwajibkan

## Quickstart — Menu Interaktif

```bash
cd ~/PROJECT/BUILD/GONKAFARM
python3 farm.py --menu
```

```
====================================================
 GONKAFARM — GonkaRouter Account Farming
====================================================
  Apikey.txt : 19 key
  9router    : 25 key
  workers    : 3
  auto-sync  : ON (prompt di akhir sesi)
----------------------------------------------------
  1. Farm batch akun-N         (input jumlah)
  2. Farm UNLIMITED            (Ctrl+C berhenti)
  3. Sinkron 9router           (dari Apikey.txt)
  4. Cek status                (saldo & jumlah key)
  5. Konfigurasi
  0. Keluar
----------------------------------------------------
  Pilih [1-5/0]:
```

Cukup **pilih angka**. Menu 1 minta jumlah akun + workers; menu 2 jalan
terus sampai Ctrl+C.

## CLI Langsung

```bash
# menu interaktif
python3 farm.py --menu

# mode unlimited: farm tanpa batas + auto-sync 9router + notifikasi 5 menit
python3 farm.py --unlimited

# mode unlimited, notifikasi tiap 60 detik
python3 farm.py --unlimited --notify 60

# batch N akun
python3 farm.py --accounts 10 --workers 3

# sinkron ulang Apikey.txt ke 9router (idempoten)
python3 farm.py --sync

# cek status
python3 farm.py --status
```

## 3 Mode Operasi

| Mode | Perintah | Kapan dipakai |
|---|---|---|
| **Menu** | `--menu` | pemakaian sehari-hari, cukup pilih angka |
| **Unlimited** | `--unlimited` | farming 24/7, sinkron otomatis, Ctrl+C berhenti |
| **Batch** | `--accounts N` | target pasti, selesai lalu exit |

### Mode Unlimited

- Farm tanpa batas akun, terus berjalan sampai **Ctrl+C**
- Setelah berhenti, muncul **prompt sync 9router** (`y/n`)
- Notifikasi statistik setiap `--notify` detik (default 300 = 5 menit):

```
[STATS] sukses=17 gagal=0 rate=7.2/min uptime=3m 9router=23 key
```

- State disimpan ke `state.json` setiap akun — aman dihentikan kapan saja,
  lanjut dari seq terakhir saat dijalankan lagi

### Multi-Instance Paralel

Sync hanya jalan **sekali di akhir sesi**, jadi beberapa instance farm
bisa jalan bersamaan tanpa bentrok:

```bash
# instance 1
cd ~/PROJECT/BUILD/GONKAFARM && python3 farm.py --unlimited

# instance 2 (folder berbeda, Apikey.txt sendiri)
cp -r ~/PROJECT/BUILD/GONKAFARM ~/PROJECT/BUILD/GONKAFARM-2
cd ~/PROJECT/BUILD/GONKAFARM-2 && rm -f Apikey.txt accounts.txt state.json
python3 farm.py --unlimited
```

Sinkron **add-only** — instance ke-2 tidak akan membuang key instance ke-1.
Detail: [docs/9router.md](docs/9router.md).

## Output

| File | Isi |
|---|---|
| `Apikey.txt` | 1 API key per baris, siap dipakai |
| `accounts.txt` | `email\|password\|date_create \| uid=<id> balance=<usdt> ch=<channel>` |
| `state.json` | checkpoint crash-safe (seq + log per akun) |

Semuanya ikut auto-sync ke 9router (`~/.9router/db/data.sqlite`).

## Struktur

```
GONKAFARM/
├── farm.py         # entry point: menu, unlimited, batch, sync, status
├── gonka.py        # GonkaRouter API client (signup → verify → reveal key)
├── mail.py         # NodexClient mail worker (OTP retrieval)
├── router9.py      # 9router sync (auto import key, anti-duplikasi)
├── solver.py       # Waryono captcha solver (cadangan, lihat solver.md)
├── config.py       # konfigurasi terpusat
├── Apikey.txt      # output: 1 key per baris
├── accounts.txt    # output: email|password|date_create
├── state.json      # checkpoint
├── docs/
│   ├── README.md       # file ini
│   ├── 9router.md      # sinkronisasi 9router
│   ├── endpoints.md    # endpoint API + reverse-engineering
│   ├── rate-limit.md   # pengukuran ceiling + strategi 3 channel
│   └── solver.md       # solver Waryono
└── logs/
```

## Alur Kerja

```
farm.py ──POST /auth/email/send──► api.gonkarouter.io
   │
   │ OTP email
   ▼
mail.nodexdigital.web.id ──► OTP code (6 digit)
   │
   ▼
POST /auth/email/verify ──► JWT token + user{id}
   │
   ▼
GET /api/me ──► balance 20 USDT
GET /api/keys + POST /reveal ──► sk-xxxx (full key)
   │
   ▼
router9.py ──► 9router providerConnections (auto, anti-duplikasi)
```

## Rate-Limit Strategy — 3 Channel

Setiap akun memakai channel rotasi: `direct` → `proxy` → `cache`.
Jika channel utama gagal, otomatis **fallback ke channel lain** dengan OTP
resend. Detail di [docs/rate-limit.md](docs/rate-limit.md).

Ceiling terukur: **~30 req/menit per IP**. Proxy `127.0.0.1:8888` (rotate IP
per request) menambah throughput.

## Konfigurasi

Lewat **menu 5** atau langsung edit `config.py`:

```python
WORKERS = 3                    # paralel worker
AUTO_SYNC_9ROUTER = True       # True = prompt y/n di akhir sesi, False = skip
ROUTER9_PREFIX = "GONKA"       # prefix nama di 9router
PROXY = "http://127.0.0.1:8888"
OTP_POLL_TIMEOUT = 180
```

Menu 5 menulis langsung ke `config.py` — efektif pada sesi berikutnya.

## Troubleshooting

| Gejala | Fix |
|---|---|
| mode unlimited STATS `sukses=0` terus | proxy/direct kena rate limit; tunggu atau turunkan `--workers` |
| `9router sync gagal` | 9router belum pernah jalan; start sekali lalu retry |
| `HTTP 403 error code: 1010` | proxy strip UA browser; cek `docs/endpoints.md` header wajib |
| `rate_limited` 429 | turunkan `WORKERS`, tambah jeda |
| key tidak muncul di 9router UI | restart 9router service (cache memory) |

Lihat juga [docs/9router.md](docs/9router.md) dan
[docs/endpoints.md](docs/endpoints.md).

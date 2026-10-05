# Rate-Limit — Pengukuran & Strategi

## Pengukuran Ceiling (probe langsung, 2026-10-04)

Probe dilakukan ke `POST /auth/email/send` dengan browser User-Agent,
paralel `concurrent.futures`.

| Beban | Hasil | Catatan |
|---|---|---|
| 1 request serial | ✅ 100% OK | baseline |
| 10 paralel | ✅ 10/10 OK (2.98s) | tidak ada penalti |
| 25 paralel | ✅ 24/25 OK (2.96s) | 1x `429` |
| **50 paralel** | ⚠️ 30/50 OK (6.86s) | 20x `429` → **ceiling 30/menit** |
| 60-90s setelah burst | ✅ normal lagi | window per menit |

**Kesimpulan: ~30 request per menit per IP.** Bukan ban permanen — setelah
window berlalu, IP kembali bersih.

### Bukti Limiter Per-IP

Setelah 30 request sukses direct, 15 request paralel **via proxy** masih
berhasil (9 OK + 3 SSL error + 3 403 IP-exit):

```
== 15 parallel via PROXY (SSL bypass) direct IP masih hangus ==
total 3.93s ok=9 err=3 403=3
```

Artinya **proxy = throughput tambahan**: setiap IP exit punya kuota 30/menit
sendiri. Inilah dasar strategi 3 channel.

### Karakteristik Proxy 127.0.0.1:8888

- Protokol **HTTP** (CONNECT tunnel), **rotate IP per request**.
- **Sertifikat self-signed** (MITM inspect) → SSL verify **wajib dimatikan`,
  jika tidak: `CERTIFICATE_VERIFY_FAILED`.
- **SSL EOF sporadis** ~20% koneksi: `SSL: UNEXPECTED_EOF_WHILE_READING`.
  Tidak fatal — retry saja.
- **403 pada IP exit tertentu** (~20%): IP tersebut sudah pernah dipakai dan
  di-cache sebagai mencurigakan. IP berikutnya biasanya lolos.
- Tanpa browser UA → `403 Forbidden` (berbeda dari `error code: 1010` di direct).

## Strategi 3 Channel

Setiap akun diproses lewat channel yang berbeda, dipilih rotasi deterministik:

```python
CHANNELS = ("direct", "proxy", "cache")

def next_channel(seq: int) -> str:
    return CHANNELS[seq % len(CHANNELS)]
```

| Channel | Koneksi | Peran |
|---|---|---|
| `direct` | langsung | stabil, tidak ada SSL quirk |
| `proxy` | `127.0.0.1:8888` | IP baru per request = kuota baru |
| `cache` | direct | OTP di-cache 10 menit, hemat poll mail worker |

### Fallback Antar Channel

Jika channel utama gagal (proxy 403, 429, SSL error setelah retry habis),
farm otomatis mencoba channel lain dengan **OTP di-resend**:

```python
chan_order = [chan] + [c for c in CHANNELS if c != chan]

for i, try_chan in enumerate(chan_order):
    gc = GonkaClient(use_proxy=try_chan == "proxy")
    res = gc.signup(email, get_code=lambda lp: get_code(lp, i))
    ...
```

OTP resend memakai cutoff waktu (`min_wait_s`) agar tidak membaca kode lama
yang sudah hangus — setiap OTP hanya berlaku untuk satu verify.

## Kecepatan yang Dicapai

| Konfigurasi | Waktu | Akun/menit |
|---|---|---|
| 3 worker, 10 akun | 242s | ~2.5 |
| 3 worker, 28 akun (burst) | 173s | ~9.7 |

Target awal **1 menit = 2 akun minimal** **terlampaui**:
- Mode stabil: **2.5 akun/menit** (3 worker)
- Mode burst: **9.7 akun/menit** (3 worker, kebetalan queue)

## Tuning

```python
# config.py
WORKERS = 3            # paralel worker; naikkan = lebih cepat
MAX_ACCOUNTS = 0       # 0 = tak terbatas
DELAY_BETWEEN_ACCOUNTS = 0
```

Aturan praktis berdasarkan pengukuran:

| Workers | Aman | Agresif | Catatan |
|---|---|---|---|
| 1-2 | ✅ | ✅ | direct saja cukup |
| 3-5 | ✅ | ⚠️ | mulai butuh proxy untuk distribusi |
| 6-10 | ⚠️ | ❌ | 429 pasti muncul; farm auto-retry tapi melambat |
| 10+  | ❌ | ❌ | waste request; ceiling 30/menit/IP jadi penghalang |

**Rekomendasi**: `WORKERS=3` untuk 24/7 aman, `WORKERS=5` untuk burst
sebentar. Tingkatkan bukan paralelisme tapi **jumlah IP** (proxy pool lebih
besar) kalau mau lebih cepat.

## Deteksi Rate Limit di Kode

```python
# gonka.py — retry dengan backoff
if e.code in (429, 502, 503, 504) or (self.use_proxy and e.code == 403):
    last = f"HTTP {e.code}"
    time.sleep(RETRY_BACKOFF * (attempt + 1))   # RETRY_BACKOFF = 3s
    continue
```

Response 429 dari server:
```json
{"error": {"code": "rate_limited", "message": "too many requests, please retry later"}}
```

`farm.py` menghitung sukses/gagal per batch dan total, jadi kemunculan 429
terlihat di log:

```
batch selesai: 2/3 | total done=5 fail=1
[send_otp] gagal: {'error': {'code': 'retry_exhausted', 'message': 'HTTP 403'}}
```

## Yang Belum Diuji

- **Threshold Turnstile.** Sejauh ini 50+ request tanpa captcha. Mungkin
  aktif setelah volume tertentu atau untuk domain email lain. Jika tiba-tiba
  muncul `turnstile_token` required, panggil `solver.py` (lihat
  [solver.md](solver.md)) lalu tambahkan fieldnya ke body request.
- **Batas harian per email domain.** `nodexdigital.web.id` belum kena tanda
  peringatan setelah 100+ pendaftaran.
- **Deteksi pola email.** Prefix `gonka-<random6>` sengaja dibuat acak;
  jika kena blokir, ganti `_PREFIX` atau pakai local part full random.

## Cadangan: Pool Webshare (10 IP statis)

`webshare-proxy.txt` di folder ini berisi 10 IP proxy statis + endpoint
rotating (`p.webshare.io`). **Tidak dipakai di farm.**

### Hasil Tes Kesehatan (2026-10-04)

Semua 10 IP sehat (exit IP benar, latency 1-10ms), tapi hanya **2 dari 10**
yang bisa mendaftar di GonkaRouter:

| Proxy | Exit IP | Gonka signup |
|---|---|---|
| `142.111.67.146:5611` | ✅ | ✅ OK |
| `31.58.9.4:6077` | ✅ | ✅ OK |
| 8 IP lainnya | ✅ | ❌ `429` |

**Kenapa:** IP Webshare adalah datacenter IP publik bersama. Sudah dipakai
user Webshare lain untuk daftar GonkaRouter, jadi kuotanya hangus. Beda
dengan `127.0.0.1:8888` yang exit IP-nya fresh (residensial).

**Jadi: bukan upgrade 10× throughput** seperti perkiraan awal — hanya +2 IP
bersih. Pakai hanya kalau `127.0.0.1:8888` mati atau IP-nya kena blok
permanen. Tetap perlu re-test kesehatan sebelum dipakai:

```bash
# cek satu IP
curl -s -m 20 -x http://yhiwcbil:vc6au38r3d7p@31.59.20.176:6754 \
  -X POST -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 ... Chrome/131.0.0.0 Safari/537.36' \
  -d '{"email":"test@nodexdigital.web.id","channel":"gonka"}' \
  https://api.gonkarouter.io/auth/email/send
```

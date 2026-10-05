# Solver — Waryono (SKIBIDIXXX)

**Prioritas utama** sesuai permintaan. File: `solver.py`.

Dokumentasi resmi: https://docs.waryono.my.id
Endpoint: `https://api.waryono.my.id`

## Kredensial

Ada di `~/credentials.txt` (sesuai pilihan kamu):

```
Waryono / SKIBIDIXXX: 3e3ddd28fd1f683584eec1989b890869
```

`solver.py` membaca dari sana (`load_key()`), atau dari env `WARYONO_API_KEY`.

```bash
# cek saldo
python3 solver.py --balance-only

# test solve turnstile
python3 solver.py example.com 0x4AAAAAAA...
```

## Spesifikasi (dari docs)

| Item | Nilai |
|---|---|
| Rate limit | **100 request / 30 detik** per apikey, timeout 300s |
| Harga turnstile | **0.1 token** per request (rate lama 2.3) |
| Kursus | 1 USD = 15.000 token |
| Metode | `in.php` POST JSON → `res.php` GET poll |
| Polling | disarankan setiap **2 detik** |

### Method & Harga

| Method | Token |
|---|---|
| turnstile | 0.1 |
| bitcocaptcha, image-to-text, rslider | 0.2 |
| hcaptcha, friendlycaptcha, cf-uam, awswaf | 0.2-0.3 |
| recapv2, recapv3, userrecaptcha | 1.0 |
| shortlink | 1.0 |

### Endpoint

**Submit:**
```bash
curl -X POST https://api.waryono.my.id/in.php \
  -H "Content-Type: application/json" \
  -d '{
    "apikey": "KEY",
    "methods": "turnstile",
    "domain": "example.com",
    "sitekey": "0x4AAAAAAABC123DEF",
    "action": "login",
    "cdata": "session_abc123"
  }'
```

> **WAJIB `Content-Type: application/json`.** Form-encoded POST kembali
> `ERROR_KEY_DOES_NOT_EXIST` (quirk server, bukan key salah).

Response:
```json
{"status": 1, "request": "12345"}
```

**Poll hasil:**
```bash
curl "https://api.waryono.my.id/res.php?apikey=KEY&action=get&id=12345&json=1"
```

| Response | Arti |
|---|---|
| `{"status":1,"request":"TOKEN"}` | selesai |
| `{"status":0,"request":"CAPCHA_NOT_READY"}` | masih proses, poll lagi |
| `{"status":0,"request":"ERROR_CAPTCHA_UNSOLVABLE"}` | gagal permanen |

**Cek saldo:**
```bash
curl "https://api.waryono.my.id/balance.php?apikey=KEY&json=1"
# {"status":1,"balance":15000}
```

### Error Code

| Code | HTTP | Pesan |
|---|---|---|
| `ERROR_KEY_DOES_NOT_EXIST` | 400 | apikey kosong |
| `ERROR_WRONG_USER_KEY` | 401 | apikey tidak valid |
| `ERROR_ZERO_BALANCE` | 402 | saldo tidak cukup |
| `ERROR_NO_SUCH_METHOD` | 400 | method tidak dikenal |
| `ERROR_WRONG_METHOD` | 405 | HTTP method salah (endpoint POST-only) |
| `ERROR_DATABASE_CONNECTION_FAILED` | 500 | DB gagal |

### Free Token (dari docs)

- Daily check-in: **+10 token/hari** (streak bonus +50 setiap 7 hari)
- Shortlink Mission: +1 token per shortlink
- Earn via Telegram bot: t.me/ski_control_api_Bot/earntoken
- Signup bonus: random 50-100 token

## Implementasi (`solver.py`)

```python
# submit + poll, return dict
solve_task("turnstile", domain="example.com", sitekey="0x4AAAA...", timeout_s=300)
# -> {"solved": True, "token": "...", "request_id": "12345", "via": "waryono", "ms": 4200}

# helper turnstile dengan retry
turnstile("example.com", "0x4AAAA...", action="", cdata="", retries=3)
# -> token string atau None
```

Fitur:
- **Rate limiter internal** (token bucket 100/30s) menghormati batas API.
- **Retry 3x** dengan backoff; `ERROR_CAPTCHA_UNSOLVABLE` langsung berhenti
  (tidak akan lolos di retry berikutnya).
- **Polling 2 detik** sesuai rekomendasi docs.
- `balance()` + `estimate_solves()` untuk cek sisa kuota.

## Status: CADANGAN (belum dipakai farm)

**GonkaRouter saat ini tidak meminta Turnstile** di endpoint manapun yang
dipakai farm ini. `solver.py` disiapkan untuk skenario jika tiba-tiba
diwajibkan.

Berdasarkan riwayat proyek sebelumnya (GROKFARM, BRIGHTDATA-FARM), Waryono
cenderung kembali `ERROR_CAPTCHA_UNSOLVABLE` untuk Turnstile di origin
tertentu (x.ai, brightdata.com). Untuk GonkaRouter belum pernah dicoba karena
memang tidak butuh.

### Cara Aktivasi Jika Nanti Butuh

1. Cari sitekey Turnstile di halaman signup:
   ```bash
   curl -s https://gonkarouter.io/ | grep -oE '0x4AAAA[A-Za-z0-9_-]+'
   ```

2. Tambahkan token ke body request di `gonka.py`:
   ```python
   # gonka.py — send_otp()
   from solver import turnstile

   tok = turnstile("gonkarouter.io", sitekey)
   body = {"email": email, "channel": CHANNEL}
   if tok:
       body["turnstile_token"] = tok
   return self._req("POST", "/auth/email/send", body=body)
   ```

3. Frontend mengirim field bernama `turnstile_token` (dilihat dari
   `Df4EdUP4.js`), jadi nama field itu yang dipakai server.

## Solver Lain (Referensi)

Sebagaimana diminta, hanya Waryono yang dipakai di proyek ini. Berikut
referensi solver lain yang pernah dipakai di farm lain (tidak diimpor):

- `https://cap.jhx.my.id/` (Nonecap, apikey `nc_live_...`) — ada di
  `~/credentials.txt`, belum pernah diuji untuk GonkaRouter.
- Camoufox local solver dari BRIGHTDATA-FARM — untuk captcha yang butuh
  browser asli; terlalu berat untuk alur HTTP-only ini.

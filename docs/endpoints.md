# GonkaRouter.io — Endpoint & Reverse-Engineering Notes

Base URL: `https://api.gonkarouter.io` (dari Nuxt runtime config
`apiBase` di HTML halaman utama; CSP `connect-src` mengizinkan host ini).

Frontend: Nuxt SPA (`/_nuxt/*.js`), Cloudflare di depan, `server: cloudflare`,
backend `via: 1.1 Caddy`.

## Alur Autentikasi (email OTP)

### 1. Kirim OTP

```
POST /auth/email/send
Content-Type: application/json

{"email": "<addr>@nodexdigital.web.id", "channel": "gonka"}
```

Response sukses:
```json
{"expires_in": 600, "resend_after": 60, "success": true}
```

Response error:
```json
{"error": {"code": "invalid_params", "message": "email and channel are required"}}
{"error": {"code": "cooldown", "message": "please wait before requesting another code"}, "retry_after": 58}
```

**Catatan penting:**
- `channel` **harus** `"gonka"` — nilai lain ditolak dengan `invalid_params`.
- **Tidak ada Turnstile di endpoint ini.** Walaupun CSP halaman mengizinkan
  `challenges.cloudflare.com` dan frontend punya field `turnstile_token`,
  server menerima request tanpa token. Field `turnstile_token` hanya dipakai
  jika dikirim; dikosongkan pun diterima.
- OTP 6 digit angka, berlaku 10 menit (`expires_in: 600`).
- Resend hanya bisa setelah 60 detik (`resend_after: 60`).

### 2. Verifikasi OTP

```
POST /auth/email/verify
Content-Type: application/json

{"email": "<addr>@nodexdigital.web.id", "channel": "gonka", "code": "123456"}
```

Response sukses (user baru):
```json
{
  "expires_in": 604800,
  "token": "eyJhbG...0O3t",
  "user": {"email": "<addr>@nodexdigital.web.id", "id": 49701}
}
```

Response error:
```json
{"error": {"code": "invalid_code", "message": "the verification code is incorrect or expired"}}
```

- `token` = JWT (223 char), berlaku 7 hari (`expires_in: 604800`).
- **OTP sekali pakai.** Verify kedua dengan kode yang sama → `invalid_code`.
- Akun dibuat otomatis saat verify pertama (tidak ada endpoint register
  terpisah). Email yang sudah terdaftar tetap mengembalikan token (login).

### 3. Ambil Data Akun

```
GET /api/me
Authorization: Bearer <token>
```
```json
{
  "balance": {"USDT": "20"},
  "usage": {"chat": {"daily_token_limit": 0, "daily_token_used": 0,
                     "monthly_cost": "0", "monthly_requests": 0,
                     "monthly_token_used": 0}},
  "user": {"email": "...", "id": 49701, "name": ""}
}
```

**Bonus 20 USDT otomatis** untuk setiap user baru — `balance.USDT == "20"`
segera setelah verify. Tidak perlu klaim manual.

### 4. Daftar API Key

```
GET /api/keys
Authorization: Bearer <token>
```
```json
{
  "items": [{
    "created_at": "2026-10-03T20:17:56.352828Z",
    "id": 50059,
    "is_default": true,
    "key_preview": "sk-Xvec…gHq2",
    "name": "default"
  }]
}
```

Satu key otomatis dibuat untuk user baru (`name: "default"`).

### 5. Reveal API Key (full)

```
POST /api/keys/<id>/reveal
Authorization: Bearer <token>
```
```json
{"id": 50059, "key": "sk-XvecmVpJ...FngHq2", "name": "default"}
```

**Hanya endpoint ini yang mengembalikan key full.** `key_preview` dan
`GET /api/keys` mem-mask dengan `…` di tengah.

### 6. Lain-lain

```
GET  /api/pricing          # no auth — daftar model + harga
GET  /v1/models            # no auth — OpenAI-compatible model list
POST /auth/google-login    # login Google (tidak dipakai farm)
POST /auth/nonce           # wallet login (tidak dipakai farm)
POST /api/email/bind       # bind email ke akun wallet
```

`/v1/chat/completions` adalah OpenAI-compatible endpoint untuk memakai key:
```bash
curl -X POST https://api.gonkarouter.io/v1/chat/completions \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{"model": "zai-org/GLM-5.3-Flash", "messages": [{"role": "user", "content": "hi"}]}'
```

## Header Wajib

Cloudflare memerlukan browser-like User-Agent. Request dengan UA default
(`curl/8.x`, `Python-urllib`) langsung kena:

```
HTTP/1.1 403
error code: 1010
```

Header yang dipakai `gonka.py`:
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/131.0.0.0 Safari/537.36
Accept: application/json
Accept-Language: en-US,en;q=0.9
Origin: https://gonkarouter.io
Referer: https://gonkarouter.io/
Content-Type: application/json (untuk POST)
```

## Rate Limit

Lihat [rate-limit.md](rate-limit.md). Singkatnya: **~30 request per menit per
IP**, window per menit (bukan ban permanen), `429 rate_limited` setelahnya.

## Model yang Tersedia (2026-10-04)

| model_id | usd_per_million |
|---|---|
| `deepseek-ai/DeepSeek-V4-Flash-0731` | 0.002276951 |
| `MiniMaxAI/MiniMax-M2.7` | 0.002276951 |
| `zai-org/GLM-5.3-Flash` | 0.002276951 |

Semua model harga sama: **0.0023 USDT per 1M token**.

## Catatan untuk Maintenance

- `channel: "gonka"` adalah nilai konstan dari frontend (`Xr="gonka"`). Jika
  gonkarouter mengganti channel, update `CHANNEL` di `config.py`.
- Verify pertama = pendaftaran. Email yang sudah terdaftar masih bisa verify
  lagi (login) dan tetap dapat token, tapi **tidak dapat bonus 20 USDT
  kedua** — bonus hanya untuk user baru.
- `key_preview` memakai karakter `…` (U+2026), bukan tiga titik ASCII. Saat
  memfilter key yang valid, cek substring `...` (3 titik) hasil response API.
- API key format: `sk-` + 45 char alfanumerik.

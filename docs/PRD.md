# PRD — GONKAFARM

## Problem

GonkaRouter.io memberi **20 USDT gratis** untuk setiap user baru + API key
dengan harga `0.0023 / 1M tokens`. Target: farming akun sebanyak mungkin
untuk mengakumulasi saldo API.

## Tujuan

1. Daftar akun otomatis dengan email temp `*@nodexdigital.web.id`
2. Klaim bonus 20 USDT user baru
3. Ekstrak full API key ke `Apikey.txt` (1 per baris)
4. Simpan data akun: `email|password|date_create`
5. **Auto-sync ke 9router** — tanpa duplikasi, tanpa intervensi manual
6. **Target kecepatan: minimal 2 akun per menit**
7. **Menu interaktif** — user cukup pilih angka

## Batasan & Asumsi

- Mail: worker CF `mail.nodexdigital.web.id` (catch-all aktif, session-based)
- Proxy: `127.0.0.1:8888` HTTP, rotate IP per request
- Solver: Waryono (prioritas utama) — **belum dibutuhkan**, Turnstile tidak
  diwajibkan GonkaRouter
- Tidak perlu `.env` khusus; kredensial solver ada di `~/credentials.txt`
  sesuai pilihan user

## Solusi

Alur HTTP-only, tanpa browser:

```
send OTP → poll mail worker → verify OTP → /api/me → /api/keys → /reveal
```

Rate-limit diatasi dengan **rotasi 3 channel** (`direct` / `proxy` / `cache`)
per akun + fallback antar channel jika gagal.

## Hasil (2026-10-04)

| Metrik | Hasil |
|---|---|
| Akun berhasil | 19/19 unlimited (3 menit) + 10/10 batch |
| Kecepatan stabil | **~7-10 akun/menit** (2-3 worker) |
| Bonus per akun | 20 USDT otomatis |
| Auto-sync 9router | ✅ setiap key, 0 duplikasi |
| Captcha dibutuhkan | ❌ tidak |
| Target 2 akun/menit | ✅ **terlampaui 3-5×** |

## Deliverables

- [x] `farm.py` — menu interaktif, mode unlimited, batch, sync, status
- [x] `router9.py` — sinkron 9router (anti-duplikasi)
- [x] `gonka.py` — API client dengan retry + proxy rotation
- [x] `mail.py` — mail worker client (thread-safe)
- [x] `solver.py` — Waryono solver (siap pakai, belum diaktifkan)
- [x] `config.py` — konfigurasi terpusat
- [x] `Apikey.txt` — output key
- [x] `accounts.txt` — output data akun
- [x] `docs/` — README, 9router, endpoints, rate-limit, solver

## Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Turnstile tiba-tiba diwajibkan | `solver.py` siap; tinggal tambah `turnstile_token` ke body (lihat docs/solver.md) |
| Rate limit diturunkan | auto-retry + backoff + fallback channel |
| Domain email di-block | prefix email random; ganti `_PREFIX` di `farm.py` |
| API key reveal diubah | cek `docs/endpoints.md` untuk format response terkini |

## Roadmap (opsional)

- [ ] PM2 `ecosystem.config.js` untuk run 24/7
- [ ] Auto-rotate mail session setiap N akun (session saat ini unlimited)
- [ ] Verifikasi saldo otomatis setelah farming
- [ ] Export gabungan semua farm (GONKA + yang lain) ke satu keypool

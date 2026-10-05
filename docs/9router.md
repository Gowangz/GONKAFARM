# 9router Sync — Auto Import API Key

Semua key hasil farm otomatis masuk ke **9router** sebagai provider
`openai-compatible-chat`, siap dipakai.

## Cara Kerja — via HTTP API

Sinkron memakai **API dashboard 9router** (`http://127.0.0.1:20128`), bukan
tulis langsung ke `data.sqlite`. Alasannya: 9router yang sedang jalan memakai
cache ORM di memori — insert langsung ke SQLite **tidak akan muncul di
dashboard** sampai service di-restart.

```
farm.py ──POST /api/auth/login──► auth_token (cookie)
       ──GET  /api/providers────► daftar connection (apiKey di-mask)
       ──POST /api/providers────► {provider, apiKey, name}  ← tambah key
```

Provider id dipakai sama dengan yang sudah ada di dashboard:

```
openai-compatible-chat-d8f0def1-8be1-4deb-b58f-241f3cb45ef6
  ├─ Key 1          apiKey: sk-*** (manual)
  ├─ Key 2          apiKey: sk-***
  ├─ GONKA <hash8>  apiKey: sk-*** (hasil script)
  └─ ...
```

Semua key bergabung di provider yang sama, tidak bikin kelompok baru.

## Anti-Duplikasi & Multi-Instance

`router9.add_to_9router()` **selalu** cek dulu:

```python
SELECT id FROM providerConnections
WHERE json_extract(data, '$.apiKey') = ?
```

Key yang sudah ada **tidak akan di-insert ulang**. `cmd_sync` hanya
memproses key yang belum ada di DB.

### Sync adalah add-only — by design

Sinkron **TIDAK pernah menghapus** key dari 9router. Ini disengaja agar
**beberapa instance farm bisa jalan paralel** tanpa saling memusnahkan
key:

```
~/PROJECT/BUILD/GONKAFARM/      ──► Apikey.txt (key A) ──┐
~/PROJECT/BUILD/GONKAFARM-2/    ──► Apikey.txt (key B) ──┴──► 9router (A + B)
```

Kalau reconcile ikut menghapus, instance ke-2 yang sync akan membuang key
instance ke-1 (sudah pernah kejadian — lihat catatan di bawah).

### Nama key anti-collision

Nama di 9router memakai short hash dari key itu sendiri:

```
GONKA d3530ccc
GONKA 7187e788
```

Index urut (`GONKA 001`, `002`) tidak bisa dipakai karena tiap instance
punya urutan sendiri — dua folder sama-sama menghasilkan `GONKA 001`.

### Purge manual

Untuk benar-benar menghapus key dari 9router:

```python
from router9 import remove_gonka
remove_gonka('sk-key-yang-mau-dihapus')
```

Atau hapus langsung via SQL. Lihat bagian "Jawaban pertanyaan 25 key"
di bawah.

## Kapan Sync Jalan

Sync **satu kali di akhir farm**, lalu muncul prompt:

```
====================================================
             2 AKUN BARU — SYNC 9ROUTER?
====================================================
  Apikey.txt : 2 key
  9router    : 0 key
  Belum sync : 2 key
----------------------------------------------------
  Mau tambahkan ke 9router? [y/N]:
```

- jawab `y` → semua key baru masuk 9router (bulk, anti-duplikasi)
- jawab `n` (default) → skip, bisa sync nanti lewat menu 3 atau `--sync`

Karena sync jalan **sekali di akhir**, dua instance farm atau lebih bisa
jalan paralel tanpa berebut kunci SQLite. Setiap instance punya `Apikey.txt`
sendiri; masing-masing sync di akhir sesi.

| Mode | Kapan prompt muncul |
|---|---|
| Menu 1 (batch) | setelah semua akun selesai |
| Menu 2 (unlimited) | saat Ctrl+C, setelah worker berhenti |
| Menu 3 / `--sync` | langsung reconcile (tidak ada prompt) |

Mode non-interaktif (pipa/stdin bukan tty) melewatkan prompt dan mencatat:

```
(non-interaktif: sync dilewati. Jalankan `farm.py --sync` manual.)
```

## Sinkron Manual

```bash
# dari Apikey.txt (idempoten — aman dijalankan berulang)
python3 farm.py --sync

# atau langsung per key
python3 -c "from router9 import add_to_9router; add_to_9router('sk-...', 'GONKA 099')"
```

## Cek Isi 9router

```bash
python3 -c "from router9 import list_gonka; print(len(list_gonka()), 'key')"

# langsung ke database
python3 -c "
import sqlite3
c = sqlite3.connect('/home/gowangz/.9router/db/data.sqlite')
for r in c.execute(\"SELECT name FROM providerConnections WHERE provider LIKE 'openai-compatible-chat-%' AND json_extract(data,'\$.apiKey')!=''\"):
    print(r[0])
"
```

## API router9.py

```python
reconcile_to_9router(keys, prefix="GONKA") -> dict
# {"added": n, "skipped": n, "failed": n} — via HTTP API, add-only

list_gonka() -> list[str]
# id connection GonkaRouter (apiKey di-mask API, jadi return id)

key_name(apikey, prefix="GONKA") -> str
# "GONKA <sha256[:8]>" — nama unik per key

# class Router9API — low level
api = Router9API()      # baca ROUTER9_PASSWORD dari .env
api.login()             # -> bool, simpan cookie
api.add(apikey, name)   # POST /api/providers
api.delete(conn_id)     # DELETE /api/providers/{id}
```

## Password — di .env

```bash
ROUTER9_PASSWORD=***    # ~/PROJECT/BUILD/GONKAFARM/.env
```

Tanpa ini sync dibatalkan dengan log `ROUTER9_PASSWORD kosong`.

## FAQ: "Setelah jawab Y, key tidak muncul di dashboard"

Ini pernah terjadi saat script masih tulis langsung ke `data.sqlite` —
9router tidak tahu ada perubahan. **Sekarang sudah diperbaiki**: sync lewat
HTTP API, jadi langsung muncul di dashboard tanpa restart.

Kalau masih tidak muncul:

1. Cek `logs/router9.log` — ada pesan error?
2. Cek `.env` — `ROUTER9_PASSWORD` terisi?
3. Cek 9router jalan: `curl -s http://127.0.0.1:20128/api/providers | head -c 50`
4. 9router versi lama mungkin portnya beda — cek `ss -tlnp | grep node`

## Konfigurasi

`config.py`:

```python
AUTO_SYNC_9ROUTER = True        # True = prompt y/n di akhir sesi, False = skip
ROUTER9_PREFIX = "GONKA"        # prefix nama di 9router UI
ROUTER9_BASE_URL = "https://api.gonkarouter.io"
```

Bisa juga diubah lewat **menu 5** (Konfigurasi) — menulis langsung ke
`config.py`.

## Default Model

Provider parent memakai `defaultModel: "zai-org/GLM-5.3-Flash"`. Model lain
yang tersedia: `deepseek-ai/DeepSeek-V4-Flash-0731`, `MiniMaxAI/MiniMax-M2.7`.
Semua harga sama (0.0023 USDT/1M token).

## Troubleshooting

| Gejala | Penyebab | Fix |
|---|---|---|
| `9router sync gagal: unable to open database file` | 9router belum pernah jalan (db belum ada) | start 9router sekali, lalu retry |
| `no such table: providerConnections` | versi 9router lebih lama | cek `sqlite3 ~/.9router/db/data.sqlite ".tables"` |
| key tidak muncul di UI 9router | 9router cache di memory | restart 9router service |
| `unique constraint failed: providerConnections.key` | key benar-benar duplikat | `add_to_9router` sudah tangani; ini cuma race condition paralel — jarang |

## Catatan Keamanan

- `router9.py` menulis langsung ke DB 9router. **Backup dulu** sebelum
  eksperimen: `cp ~/.9router/db/data.sqlite ~/.9router/db/backups/`.
- Jangan jalankan 2 instance farm bersamaan — lock SQLite hanya per-proses,
  bisa conflict. Satu instance unlimited saja sudah cukup.

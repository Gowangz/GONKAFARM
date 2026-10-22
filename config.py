# ── GONKAFARM core ──────────────────────────────────────────────
GONKA_API_BASE = "https://api.gonkarouter.io"
GONKA_MAIL_BASE = "https://mail.nodexdigital.web.id"
MAIL_DOMAIN = "nodexdigital.web.id"
CHANNEL = "gonka"

# ── Rate-limit strategy (3 modes, rotated per account) ──────────
# Terukur: ceiling ~30 req/menit per IP. Proxy = rotating IP per request.
# Oxylabs (`pr.oxylabs.io`) kembali 502 session expired → pindah ke proxy
# lokal 127.0.0.1:8888 (rotating, exit IP fresh, terbukti OK ke Gonka 51.8s).
PROXY = "http://127.0.0.1:8888"
REQUEST_TIMEOUT = 45

# ── Turnstile (diwajibkan sejak 2026) ─────────────────────────────
# Nilai dari halaman /auth/register; dikirim via field turnstile_token.
TURNSTILE_SITEKEY = "0x4AAAAAAFcbQ4RGI69Sc6pz"

# ── Timing (detik) ──────────────────────────────────────────────
OTP_POLL_INTERVAL = 3
OTP_POLL_TIMEOUT = 180
RETRY_MAX = 4
RETRY_BACKOFF = 3

# ── Output files (relatif ke folder ini) ────────────────────────
APIKEY_FILE = "Apikey.txt"
ACCOUNTS_FILE = "accounts.txt"
STATE_FILE = "state.json"
LOG_FILE = "logs/gonkafarm.log"
BATCH_DIR = "output"   # folder induk snapshot per-batch (batch-N-ts-N)

# ── Runtime ─────────────────────────────────────────────────────
WORKERS = 1
MAX_ACCOUNTS = 0       # 0 = tak terbatas
DELAY_BETWEEN_ACCOUNTS = 45   # cooldown antar akun (detik), hindari 429 server

# ── State siklus ────────────────────────────────────────────────
# True: setelah farm terbatas selesai, state.json di-backup &
# di-reset ke seq 0 → `--accounts N` berikutnya = N akun baru lagi,
# tanpa mengurus state manual. Sejarah tetap di state_history.json.
AUTO_RESET_STATE = True

# ── 9router auto-sync ───────────────────────────────────────────
# Setiap key baru otomatis masuk ke 9router (openai-compatible provider).
# Lihat docs/9router.md
AUTO_SYNC_9ROUTER = True
ROUTER9_PREFIX = "GONKA"
ROUTER9_BASE_URL = "https://api.gonkarouter.io"

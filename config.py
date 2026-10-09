# ── GONKAFARM core ──────────────────────────────────────────────
GONKA_API_BASE = "https://api.gonkarouter.io"
GONKA_MAIL_BASE = "https://mail.nodexdigital.web.id"
MAIL_DOMAIN = "nodexdigital.web.id"
CHANNEL = "gonka"

# ── Rate-limit strategy (3 modes, rotated per account) ──────────
# Terukur: ceiling ~30 req/menit per IP. Proxy = IP baru per request.
PROXY = "http://customer-resi_8ca33b6f-sessid-0817767014-sesstime-10:SVfb3=otN13f@pr.oxylabs.io:7777"
REQUEST_TIMEOUT = 45

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

# ── Runtime ─────────────────────────────────────────────────────
WORKERS = 6
MAX_ACCOUNTS = 0       # 0 = tak terbatas
DELAY_BETWEEN_ACCOUNTS = 0   # jeda setelah akun selesai (mode turbo)

# ── 9router auto-sync ───────────────────────────────────────────
# Setiap key baru otomatis masuk ke 9router (openai-compatible provider).
# Lihat docs/9router.md
AUTO_SYNC_9ROUTER = True
ROUTER9_PREFIX = "GONKA"
ROUTER9_BASE_URL = "https://api.gonkarouter.io"

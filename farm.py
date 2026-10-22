#!/usr/bin/env python3
"""GONKAFARM — mass account farming untuk GonkaRouter.io.

Daftar akun dengan email temp *@nodexdigital.web.id, klaim bonus 20 USDT
user baru, ekstrak API key ke Apikey.txt (1 per baris), simpan data akun.

Rate-limit strategy — 3 channel diputar per akun:
  direct  : koneksi langsung (ceiling ~30 req/menit per IP)
  proxy   : http://127.0.0.1:8888 (rotate IP per request)
  cache   : direct + cache token email/kode yang masih berlaku

Penggunaan:
  ./farm.py                    # siklus tak terbatas
  ./farm.py --accounts 5       # berhenti setelah 5 akun
  ./farm.py --workers 3        # paralel worker
  ./farm.py --probe            # ukur ceiling rate limit (mode uji)
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import random
import re
import string
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (ACCOUNTS_FILE, APIKEY_FILE, AUTO_RESET_STATE, AUTO_SYNC_9ROUTER,
                    BATCH_DIR, CHANNEL, DELAY_BETWEEN_ACCOUNTS, GONKA_API_BASE, LOG_FILE,
                    MAIL_DOMAIN, MAX_ACCOUNTS, OTP_POLL_TIMEOUT, PROXY,
                    REQUEST_TIMEOUT, RETRY_MAX, ROUTER9_PREFIX, WORKERS)
from gonka import GonkaClient, log
from mail import MailClient

BASE_DIR = Path(__file__).resolve().parent
APIKEY_PATH = BASE_DIR / APIKEY_FILE
ACCOUNTS_PATH = BASE_DIR / ACCOUNTS_FILE
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / LOG_FILE
BATCH_DIR = BASE_DIR / BATCH_DIR  # output/ — snapshot per batch

_lock = threading.Lock()
_stats = {"done": 0, "fail": 0, "started": time.time()}
_stopping = threading.Event()

# ── state (crash-safe) ──────────────────────────────────────────


def load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"seq": 0, "accounts": []}


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_PATH)


def append_apikey(key: str) -> None:
    with _lock:
        with open(APIKEY_PATH, "a") as f:
            f.write(key + "\n")


def append_account(email: str, password: str, date_create: str, extra: str = "") -> None:
    with _lock:
        with open(ACCOUNTS_PATH, "a") as f:
            f.write(f"{email}|{password}|{date_create}{(' | ' + extra) if extra else ''}\n")


def _backup_and_reset_state(state: dict) -> None:
    """Backup state.json → state_history.json lalu reset seq ke 0.

    Dipanggil setelah siklus terbatas selesai bersih. Sejarah akun tetap
    tersimpan (> 0 akun), tapi seq di-nol-kan supaya perintah berikutnya
    (`--accounts N`) selalu berarti N akun baru.
    """
    if not state.get("accounts") or state.get("seq", 0) <= 1:
        return
    try:
        hist_path = BASE_DIR / "state_history.json"
        hist = {}
        if hist_path.is_file():
            try:
                hist = json.loads(hist_path.read_text())
            except Exception:
                hist = {}
        last = {"seq": state["seq"], "accounts": state["accounts"]}
        hist[str(int(time.time()))] = last
        hist_path.write_text(json.dumps(hist, indent=2))
        log(f"state di-backup ke state_history.json (seq={state['seq']})")
    except Exception as e:
        log(f"backup state gagal: {e}")
    state["seq"] = 0
    state["accounts"] = []
    save_state(state)
    log("state di-reset ke seq=0 — run berikutnya = N akun baru.")


def _read_keys() -> list[str]:
    """Kunci dari Apikey.txt (toleran file belum ada)."""
    try:
        return [l.strip() for l in open(APIKEY_PATH) if l.strip()]
    except FileNotFoundError:
        return []


def _next_batch_no() -> int:
    """Nomor batch berikutnya, dihitung dari folder output yang sudah ada."""
    try:
        if BATCH_DIR.is_dir():
            ns = [int(p.name.split("-")[1]) for p in BATCH_DIR.iterdir()
                  if p.is_dir() and p.name.startswith("batch-")]
            return (max(ns) + 1) if ns else 1
        return 1
    except Exception:
        return 1


def _write_batch_folder(done: int) -> None:
    """Snapshot batch ini ke output/batch-<n>-<ts>-<done>/ (apikey + accounts)."""
    try:
        ts = time.strftime("%Y%m%d-%H%M%S")
        n = _next_batch_no()
        folder = BATCH_DIR / f"batch-{n:02d}-{ts}-{done}"
        folder.mkdir(parents=True, exist_ok=True)
        # apikey murni: 1 key/baris (semua key yang sudah pernah ada → difilter
        # dari Apikey.txt; batch ini = N baris terakhir sesuai done)
        keys = _read_keys()
        lines = keys[-done:] if done else keys
        (folder / "apikey.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        # accounts untuk batch ini: baris termutakhir sebanyak done
        try:
            acc_lines = [l for l in open(ACCOUNTS_PATH) if l.strip()]
        except FileNotFoundError:
            acc_lines = []
        acc = acc_lines[-done:] if done else acc_lines
        (folder / "accounts.txt").write_text("".join(acc) if acc else "")
        log(f"batch output -> {folder.relative_to(BASE_DIR)} "
            f"(apikey={len(lines)} accounts={len(acc)})")
    except Exception as e:
        log(f"gagal tulis batch folder: {e}")


def _auto_sync_batch() -> None:
    """Import key hasil batch ini ke 9router (add-only, pakai router9)."""
    key = _read_keys()
    if not key:
        return
    try:
        from router9 import reconcile_to_9router
        r = reconcile_to_9router(key, prefix=ROUTER9_PREFIX)
        log(f"auto-sync 9router: +{r['added']} baru, {r['skipped']} sudah ada, "
            f"{r['failed']} gagal (total {len(_read_keys())} key)")
    except Exception as e:
        log(f"auto-sync 9router gagal: {e}")


# ── email generator ─────────────────────────────────────────────

_PREFIX = "gonka"


def gen_local_part(seq: int) -> str:
    """gonka-7f3a2b · random suffix agar tidak terlihat berpola."""
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{_PREFIX}-{tag}"


# ── rate-limit strategy: 3 channel ──────────────────────────────

CHANNELS = ("direct", "proxy", "cache")


def next_channel(seq: int) -> str:
    """Rotasi deterministik per akun: direct -> proxy -> cache -> ulang."""
    return CHANNELS[seq % len(CHANNELS)]


class OtpCache:
    """Lapis 'cache': simpan mapping email -> (otp, expired_at) saat probing.

    Jika email yang sama dikirimi OTP lagi dalam masa berlaku, ambil dari cache
    tanpa polling mail worker. Mengurangi beban mail worker saat burst.

    Catatan: kode yang sudah dipakai verify harus di-invalidasi via pop(),
    sebaliknya verify kedua akan memakai kode lama yang sudah hangus.
    """

    def __init__(self) -> None:
        self._m: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def put(self, email: str, code: str, ttl: int = 600) -> None:
        with self._lock:
            self._m[email] = (code, time.time() + ttl)

    def get(self, email: str) -> str | None:
        with self._lock:
            v = self._m.get(email)
            if not v:
                return None
            code, exp = v
            if time.time() > exp:
                self._m.pop(email, None)
                return None
            return code

    def pop(self, email: str) -> str | None:
        """Ambil + hapus. Dipakai setelah verify agar retry tidak pakai kode lama."""
        with self._lock:
            v = self._m.pop(email, None)
            if not v:
                return None
            code, exp = v
            return None if time.time() > exp else code


_otp_cache = OtpCache()


# ── worker ──────────────────────────────────────────────────────


def register_one(seq: int, mail: MailClient, target: int) -> bool:
    chan = next_channel(seq)
    local = gen_local_part(seq)
    email = f"{local}@{MAIL_DOMAIN}"
    password = f"Nodex123!{local[-4:]}"

    log(f"[#{seq}] {email} via {chan}")
    try:
        addr = mail.create_inbox(local)
        if addr.lower() != email.lower():
            log(f"[#{seq}] inbox mismatch: {addr}")
            return False
    except Exception as e:
        log(f"[#{seq}] inbox gagal: {e}")
        return False

    # urutan channel: utama dulu, lalu fallback. Proxy 8888 sering 403 di IP
    # tertentu; direct aman selama belum menyentuh ceiling ~30/menit.
    chan_order = [chan] + [c for c in CHANNELS if c != chan]

    def get_code(lp: str, attempt: int = 0) -> str | None:
        hit = _otp_cache.get(email)
        if hit:
            log(f"[#{seq}] OTP dari cache")
            return hit
        # attempt > 0 = fallback: OTP sebelumnya mungkin hangus, kirim ulang dan
        # hanya baca email yang masuk setelah permintaan ini.
        if attempt > 0:
            again = GonkaClient(use_proxy=False).send_otp(email)
            if not again.get("success"):
                log(f"[#{seq}] resend OTP gagal: {again}")
                return None
            min_wait = 2.0
            t0 = time.time()
            code = mail.wait_otp(lp, timeout_s=OTP_POLL_TIMEOUT, min_wait_s=min_wait)
            log(f"[#{seq}] OTP kedua dalam {time.time()-t0:.0f}s")
        else:
            code = mail.wait_otp(lp, timeout_s=OTP_POLL_TIMEOUT)
        if code:
            _otp_cache.put(email, code)
        return code

    for i, try_chan in enumerate(chan_order):
        gc = GonkaClient(use_proxy=try_chan == "proxy")
        try:
            res = gc.signup(email, get_code=lambda lp: get_code(lp, i))
        except Exception as e:
            log(f"[#{seq}] exception via {try_chan}: {e}")
            res = None
        if res:
            api_key = res["api_key"]
            append_apikey(api_key)
            append_account(email, password, time.strftime("%Y-%m-%d %H:%M:%S"),
                           extra=f"uid={res.get('user_id')} balance={res.get('balance')} ch={try_chan}")
            log(f"[#{seq}] OK  key=...{api_key[-6:]}  balance={res.get('balance')}")
            return True
        # OTP sudah dipakai (atau hangus) -> bersihkan agar tidak dipakai ulang
        _otp_cache.pop(email)
        log(f"[#{seq}] gagal via {try_chan}, coba channel berikutnya")

    log(f"[#{seq}] GAGAL total ({email})")
    return False


def worker(mail: MailClient, q: "queue.Queue[int]", results: dict) -> None:
    """Konsumsi seq dari queue hingga ketik sentinel (None = selesai)."""
    while True:
        seq = q.get()  # memblokir sampai ada tugas atau sentinel
        if seq is None:
            return
        ok = register_one(seq, mail, 0)
        with _lock:
            results[seq] = ok
            _stats["done" if ok else "fail"] += 1
        if DELAY_BETWEEN_ACCOUNTS > 0:
            time.sleep(DELAY_BETWEEN_ACCOUNTS)
        q.task_done()
# ── main ────────────────────────────────────────────────────────


def cmd_farm(args) -> None:
    n = args.accounts or MAX_ACCOUNTS or 0
    workers = max(1, args.workers or WORKERS)
    log(f"GONKAFARM start | target={n or 'unlimited'} workers={workers} proxy={PROXY}")

    state = load_state()
    start_seq = state["seq"] + 1
    _args_limited = bool(args.accounts)  # siklus terbatas → reset state setelah selesai

    mail = MailClient()
    mail.new_session()
    log(f"mail session: {mail.session_id[:8]}...")

    seq = start_seq
    limit = start_seq + n - 1 if n else None  # target relatif: N akun baru
    while True:
        batch = []
        for _ in range(workers):
            if limit and seq > limit:
                break
            batch.append(seq)
            seq += 1
        if not batch:
            break
        batch_max = max(batch)  # simpan sebelum worker menghabiskan queue
        q: "queue.Queue[int]" = queue.Queue()
        for s in batch:
            q.put(s)
        results: dict[int, bool] = {}
        threads = [threading.Thread(target=worker, args=(mail, q, results),
                                    daemon=True) for _ in range(len(batch))]
        for t in threads:
            t.start()
        for _ in threads:  # sentinel: worker keluar setelah batch habis
            q.put(None)
        for t in threads:
            t.join()

        with _lock:
            state["seq"] = batch_max
            for s, ok in results.items():
                state["accounts"].append({"seq": s, "ok": ok,
                                          "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
            save_state(state)

        ok_n = sum(1 for v in results.values() if v)
        log(f"batch selesai: {ok_n}/{len(batch)} | total done={_stats['done']} fail={_stats['fail']}")

        if limit and seq > limit:
            break
        if args.cycle_delay > 0:
            time.sleep(args.cycle_delay)

    log(f"SELESAI. sukses={_stats['done']} gagal={_stats['fail']} "
        f"elapsed={time.time() - _stats['started']:.0f}s")
    log(f"apikey  : {APIKEY_PATH}")
    log(f"accounts: {ACCOUNTS_PATH}")

    # Batch-output: simpan hasil batch ini ke folder terpisah
    if _args_limited and _stats["done"] > 0:
        _write_batch_folder(_stats["done"])

    if _stats["done"] > 0:
        if AUTO_SYNC_9ROUTER:
            # Mode otomatis: langsung import key baru ke 9router (tanpa prompt)
            _auto_sync_batch()
        else:
            prompt_sync(f"{_stats['done']} AKUN BARU — SYNC 9ROUTER?")

    # Siklus terbatas selesai bersih → backup & reset state, supaya run
    # berikutnya (`--accounts N`) selalu berarti N akun baru tanpa urus state.
    if _args_limited and AUTO_RESET_STATE:
        _backup_and_reset_state(state)
    elif not _args_limited and not _stopping.is_set():
        # mode unlimited berhenti via Ctrl+C: jangan reset (biar bisa lanjut)
        pass


def cmd_probe(args) -> None:
    """Ukur ceiling rate limit: tembak N request paralel per channel."""
    n = args.probe
    log(f"PROBE mode: {n} request paralel")
    import concurrent.futures as cf

    def hit(i: int, use_proxy: bool):
        gc = GonkaClient(use_proxy=use_proxy)
        t0 = time.time()
        r = gc.send_otp(f"probe-{int(time.time())}-{i}@{MAIL_DOMAIN}")
        return (i, "proxy" if use_proxy else "direct",
                r.get("success", False), r.get("error", {}).get("code", ""),
                round(time.time() - t0, 2))

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        res = list(ex.map(lambda i: hit(i, args.channel == "proxy"), range(n)))
    dt = time.time() - t0
    ok = sum(1 for r in res if r[2])
    log(f"ch={args.channel} n={n} ok={ok} time={dt:.2f}s")
    for r in sorted(res, key=lambda x: x[0]):
        print(r)


def cmd_unlimited(args) -> None:
    """Mode unlimited: farm tanpa batas + auto-sync 9router + notifikasi periodik."""
    workers = max(1, args.workers or WORKERS)
    log(f"GONKAFARM UNLIMITED | workers={workers} notify={args.notify}s proxy={PROXY}")

    state = load_state()
    seq = state["seq"] + 1
    mail = MailClient()
    mail.new_session()
    log(f"mail session: {mail.session_id[:8]}...")

    q: "queue.Queue[int]" = queue.Queue()
    results: dict[int, bool] = {}
    stop = threading.Event()

    def notifier() -> None:
        """Cetak ringkasan setiap args.notify detik."""
        last_done = 0
        while not stop.is_set():
            if stop.wait(args.notify):
                return
            with _lock:
                done, fail = _stats["done"], _stats["fail"]
            rate = (done - last_done) / (args.notify / 60)
            last_done = done
            uptime = time.time() - _stats["started"]
            try:
                from router9 import list_gonka
                r9 = len(list_gonka())
            except Exception:
                r9 = -1
            log(f"[STATS] sukses={done} gagal={fail} rate={rate:.1f}/min "
                f"uptime={uptime/60:.0f}m 9router={r9} key")

    threads = [threading.Thread(target=worker, args=(mail, q, results),
                                daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    if args.notify > 0:
        threading.Thread(target=notifier, daemon=True).start()

    try:
        while not stop.is_set():
            q.put(seq)
            seq += 1
            with _lock:
                state["seq"] = seq - 1
                save_state(state)
            # jeda kecil agar queue tidak membengkak jauh di depan worker
            while q.qsize() >= workers * 3:
                if stop.is_set():
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        log("dihentikan user (Ctrl+C), menunggu worker...")
        stop.set()
        # kirim sentinel ke semua worker agar keluar dari q.get()
        for _ in range(workers):
            q.put(None)
    for t in threads:
        t.join(timeout=OTP_POLL_TIMEOUT + 30)

    with _lock:
        state["seq"] = seq - 1
        save_state(state)
    log(f"BERHENTI. sukses={_stats['done']} gagal={_stats['fail']}")
    if _stats["done"] > 0:
        prompt_sync(f"{_stats['done']} AKUN BARU — SYNC 9ROUTER?")


def cmd_menu(args) -> None:
    """Menu utama interaktif."""
    while True:
        print()
        print("=" * 52)
        print(" GONKAFARM — GonkaRouter Account Farming".center(52))
        print("=" * 52)
        try:
            r9 = len(__import__("router9").list_gonka())
        except Exception:
            r9 = 0
        try:
            keys = sum(1 for _ in open(APIKEY_PATH))
        except Exception:
            keys = 0
        print(f"  Apikey.txt : {keys} key")
        print(f"  9router    : {r9} key")
        print(f"  workers    : {WORKERS}")
        print(f"  auto-sync  : {'ON' if AUTO_SYNC_9ROUTER else 'OFF'}")
        print("-" * 52)
        print("  1. Farm batch akun-N         (input jumlah)")
        print("  2. Farm UNLIMITED            (Ctrl+C berhenti)")
        print("  3. Sinkron 9router           (dari Apikey.txt)")
        print("  4. Cek status                (saldo & jumlah key)")
        print("  5. Konfigurasi")
        print("  0. Keluar")
        print("-" * 52)
        p = input("  Pilih [1-5/0]: ").strip()

        if p == "1":
            n = input("  Jumlah akun (default 5): ").strip()
            try:
                n = int(n) if n else 5
            except ValueError:
                n = 5
            w = input(f"  Workers (default {WORKERS}): ").strip()
            try:
                w = int(w) if w else WORKERS
            except ValueError:
                w = WORKERS
            args.accounts, args.workers = n, w
            args.cycle_delay = 0
            cmd_farm(args)
        elif p == "2":
            args.workers = 0
            args.notify = 300
            cmd_unlimited(args)
        elif p == "3":
            cmd_sync(args)
        elif p == "4":
            cmd_status(args)
        elif p == "5":
            cmd_config(args)
        elif p in ("0", "q", "exit"):
            print("  bye.")
            return
        else:
            print("  pilihan tidak dikenal")


def cmd_sync(args) -> None:
    """Reconcile Apikey.txt ↔ 9router: tambah yang baru, buang yang tak ada."""
    keys = [l.strip() for l in open(APIKEY_PATH) if l.strip()]
    if not keys:
        print("  Apikey.txt kosong — tidak ada yang disinkron.")
        return
    from router9 import reconcile_to_9router, list_gonka as _list_gonka
    r = reconcile_to_9router(keys, prefix=ROUTER9_PREFIX)
    if r["failed"]:
        log(f"sinkron: +{r['added']} baru, {r['skipped']} sudah ada, "
            f"{r['failed']} GAGAL (total {len(_list_gonka())}) — "
            "cek logs/router9.log")
    else:
        log(f"sinkron: +{r['added']} baru, {r['skipped']} sudah ada "
            f"(total {len(_list_gonka())})")


def list_gonka() -> list[str]:
    """Daftar apiKey GonkaRouter yang sudah ada di 9router DB."""
    try:
        from router9 import list_gonka as _lg
        return _lg()
    except Exception:
        return []


def prompt_sync(header: str) -> None:
    """Tanya user apakah mau sync hasil farm ke 9router.

    AUTO_SYNC_9ROUTER=False menonaktifkan prompt seluruhnya (skip tanpa tanya).
    Mode non-interaktif (stdin bukan tty) juga skip.
    """
    if not AUTO_SYNC_9ROUTER:
        log("auto-sync 9router dimatikan (AUTO_SYNC_9ROUTER=False) — skip.")
        return
    if not sys.stdin.isatty():
        log("(non-interaktif: sync dilewati. Jalankan `farm.py --sync` manual.)")
        return
    print()
    print("=" * 52)
    print(f" {header}".center(52))
    print("=" * 52)
    # API mem-mask apiKey, jadi hitung key yang sudah sync dari state file
    try:
        from router9 import _load_sent
        sent = _load_sent()
    except Exception:
        sent = set()
    try:
        keys = [l.strip() for l in open(APIKEY_PATH) if l.strip()]
    except FileNotFoundError:
        keys = []
    baru = [k for k in keys if k not in sent]
    print(f"  Apikey.txt : {len(keys)} key")
    print(f"  9router    : {len(list_gonka())} key")
    print(f"  Belum sync : {len(baru)} key")
    print("-" * 52)
    if not baru:
        print("  Semua key sudah tersinkron. Tidak ada yang perlu ditambah.")
        return
    while True:
        p = input("  Mau tambahkan ke 9router? [y/N]: ").strip().lower()
        if p in ("y", "ya", "yes"):
            cmd_sync(None)
            return
        if p in ("", "n", "no", "tidak"):
            print("  Skip. Jalankan `farm.py --sync` nanti kapan saja.")
            return


def cmd_status(args) -> None:
    """Cek status akun: jumlah key & key valid di Apikey.txt."""
    from gonka import log as glog
    log_line = f"{time.strftime('%H:%M:%S')} [STATUS] Apikey.txt={len(_read_keys())} 9router={len(list_gonka())} up={time.time()-_stats['started']:.0f}s"
    print(log_line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(log_line + "\n")
    except Exception:
        pass


def cmd_config(args) -> None:
    """Tampilkan & ubah konfigurasi runtime (tulis ke config.py)."""
    while True:
        print()
        print("  Konfigurasi (format: KUNCI = NILAI)")
        print(f"  1. workers        = {WORKERS}")
        print(f"  2. auto_sync_9r   = {AUTO_SYNC_9ROUTER}")
        print(f"  3. router9_prefix = {ROUTER9_PREFIX}")
        print(f"  4. proxy          = {PROXY}")
        print("  0. kembali")
        p = input("  Pilih [1-4/0]: ").strip()
        if p == "0" or not p:
            return
        key_map = {"1": "WORKERS", "2": "AUTO_SYNC_9ROUTER", "3": "ROUTER9_PREFIX", "4": "PROXY"}
        key = key_map.get(p)
        if not key:
            print("  tidak dikenal")
            continue
        val = input(f"  {key} baru: ").strip()
        if not val:
            continue
        try:
            _persist_config(key, val)
            print(f"  ✓ {key} = {val} (mulai efektif sesi berikutnya)")
        except Exception as e:
            print(f"  gagal: {e}")


def _persist_config(key: str, val: str) -> None:
    """Tulis ulang satu baris di config.py."""
    import re as _re
    cfg_path = Path(__file__).resolve().parent / "config.py"
    text = cfg_path.read_text()
    if key in ("WORKERS",):
        new_line = f"{key} = {int(val)}"
    elif key in ("AUTO_SYNC_9ROUTER",):
        new_line = f"{key} = {'True' if val.lower() in ('1', 'true', 'on', 'ya') else 'False'}"
    else:
        new_line = f'{key} = "{val}"'
    pattern = _re.compile(rf"^{key}\s*=.*$", _re.M)
    if not pattern.search(text):
        raise RuntimeError(f"{key} tidak ditemukan di config.py")
    cfg_path.write_text(pattern.sub(new_line, text, count=1))


def main() -> None:
    p = argparse.ArgumentParser(description="GONKAFARM — GonkaRouter account farming")
    p.add_argument("--accounts", type=int, default=0, help="jumlah akun (0 = tak terbatas)")
    p.add_argument("--workers", type=int, default=0, help="paralel worker")
    p.add_argument("--cycle-delay", type=int, default=0, help="jeda antar batch (detik)")
    p.add_argument("--unlimited", action="store_true",
                   help="mode tak terbatas + auto-sync 9router")
    p.add_argument("--notify", type=int, default=300,
                   help="interval notifikasi statistik (detik, default 300)")
    p.add_argument("--menu", action="store_true", help="menu interaktif")
    p.add_argument("--sync", action="store_true", help="sinkron Apikey.txt ke 9router")
    p.add_argument("--status", action="store_true", help="cek saldo & jumlah key")
    p.add_argument("--probe", type=int, default=0, help="mode uji rate limit: N request paralel")
    p.add_argument("--channel", default="direct", choices=["direct", "proxy"],
                   help="channel untuk probe")
    args = p.parse_args()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.menu:
        cmd_menu(args)
    elif args.unlimited:
        cmd_unlimited(args)
    elif args.sync:
        cmd_sync(args)
    elif args.status:
        cmd_status(args)
    elif args.probe:
        cmd_probe(args)
    else:
        cmd_farm(args)


if __name__ == "__main__":
    main()

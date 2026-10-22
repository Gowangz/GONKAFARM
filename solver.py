"""Waryono (SKIBIDIXXX) captcha solver — prioritas utama.

Dokumentasi resmi: https://docs.waryono.my.id
Endpoint : https://api.waryono.my.id/in.php (POST JSON) / res.php (GET poll)
Rate     : 100 request / 30 detik per apikey, timeout 300s auto-expire
Harga    : turnstile 0.1 token (rate lama 2.3) · 1 USD = 15.000 token

Catatan penting (dari docs):
  - in.php WAJIB Content-Type: application/json. Form-encoded akan
    mengembalikan ERROR_KEY_DOES_NOT_EXIST (quirk server).
  - Polling res.php disarankan setiap 2 detik.
  - apikey bisa di body JSON atau query string.

GonkaRouter saat ini TIDAK meminta turnstile di /auth/email/send,
sehingga solver ini menjadi lapis cadangan jika tiba-tiba dipaksa.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.waryono.my.id"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# docs: Max 100 request per 30 detik per API key
RATE_WINDOW_S = 30
RATE_MAX = 100

METHOD_COST = {  # token per request (docs "Harga per Request")
    "turnstile": 0.1, "bitcocaptcha": 0.2, "image-to-text": 0.2,
    "rslider": 0.2, "antibot": 0.3, "pcaptcha": 0.3,
    "hcaptcha": 0.2, "recapv2": 1.0, "recapv3": 1.0,
    "cf-uam": 0.3, "friendlycaptcha": 0.3, "awswaf": 0.3,
    "shortlink": 1.0, "faucetpay": 0.3, "geetest": 0.3,
}


def load_key() -> str:
    """Ambil WARYONO_API_KEY dari env atau credentials.txt di home."""
    k = (os.getenv("WARYONO_API_KEY") or "").strip()
    if k:
        return k
    for p in (
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.expanduser("~/credentials.txt"),
    ):
        if not os.path.isfile(p):
            continue
        try:
            for line in open(p):
                line = line.strip()
                if line.startswith("Waryono") and ":" in line:
                    v = line.split(":", 1)[1].strip()
                    if v:
                        return v
        except Exception:
            pass
    return ""


class _RateLimiter:
    """Token bucket sederhana: max RATE_MAX per RATE_WINDOW_S."""

    def __init__(self) -> None:
        self.hits: list[float] = []

    def wait(self) -> None:
        now = time.time()
        self.hits = [t for t in self.hits if now - t < RATE_WINDOW_S]
        if len(self.hits) >= RATE_MAX:
            sleep_for = RATE_WINDOW_S - (now - self.hits[0]) + 0.2
            if sleep_for > 0:
                time.sleep(sleep_for)
        self.hits.append(time.time())


_rl = _RateLimiter()


def _post_json(path: str, payload: dict, timeout: int = 60) -> dict:
    _rl.wait()
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://waryono.my.id",
                "Referer": "https://waryono.my.id/"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get_json(url: str, timeout: int = 60) -> dict:
    _rl.wait()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def balance() -> float:
    r = _get_json(f"{BASE}/balance.php?apikey={urllib.parse.quote(load_key())}&json=1")
    if r.get("status") != 1:
        raise RuntimeError(f"waryono balance error: {r}")
    return float(r["balance"])


def estimate_solves(method: str = "turnstile") -> int:
    return int(balance() // METHOD_COST.get(method, 0.1))


def solve_task(method: str, timeout_s: int = 300, **params) -> dict:
    """Submit + poll. Return {solved, token|error, request_id}."""
    key = load_key()
    if not key:
        return {"solved": False, "error": "no WARYONO_API_KEY"}
    payload = {"apikey": key, "methods": method, "json": 1}
    payload.update({k: v for k, v in params.items() if v is not None})
    t0 = time.time()
    try:
        cr = _post_json("/in.php", payload)
    except urllib.error.HTTPError as e:
        return {"solved": False, "error": f"in.php HTTP {e.code}"}
    except Exception as e:
        return {"solved": False, "error": f"in.php: {e}"}
    if cr.get("status") != 1:
        return {"solved": False, "error": str(cr.get("request"))}
    rid = str(cr.get("request"))

    deadline = t0 + timeout_s
    while time.time() < deadline:
        time.sleep(2)  # docs: polling disarankan setiap 2 detik
        try:
            pr = _get_json(
                f"{BASE}/res.php?apikey={urllib.parse.quote(key)}"
                f"&action=get&id={urllib.parse.quote(rid)}&json=1"
            )
        except Exception:
            continue
        req = str(pr.get("request", ""))
        if pr.get("status") == 1:
            if req and req != "OK_REPORTED" and len(req) > 40:
                return {"solved": True, "token": req, "request_id": rid,
                        "via": "waryono", "ms": int((time.time() - t0) * 1000)}
            return {"solved": False, "error": f"odd token: {req[:80]}"}
        if req.startswith("ERROR_"):
            return {"solved": False, "error": req, "request_id": rid}
        # CAPCHA_NOT_READY -> lanjut polling
    return {"solved": False, "error": "waryono timeout", "request_id": rid}


def turnstile(domain: str, sitekey: str, action: str = "", cdata: str = "",
              retries: int = 3, timeout_s: int = 300) -> str | None:
    """Solve Turnstile. domain = bare host (docs: domain target)."""
    last = {"solved": False, "error": "no attempt"}
    for i in range(max(1, retries)):
        last = solve_task(
            "turnstile", timeout_s=timeout_s,
            domain=domain, url=f"https://{domain}",
            sitekey=sitekey, action=action or None, cdata=cdata or None,
        )
        if last.get("solved"):
            return last["token"]
        # ERROR_CAPTCHA_UNSOLVABLE tidak akan lolos di retry berikutnya
        if "UNSOLVABLE" in str(last.get("error")):
            break
        time.sleep(1.2 + i)
    return None


if __name__ == "__main__":
    import sys

    key = load_key()
    print(f"key loaded : {bool(key)}")
    if key:
        try:
            print(f"balance    : {balance()} token | ~{estimate_solves()} turnstile")
        except Exception as e:
            print(f"balance err: {e}")
    if len(sys.argv) > 1 and sys.argv[1] != "--balance-only":
        d = sys.argv[1]
        s = sys.argv[2] if len(sys.argv) > 2 else ""
        tok = turnstile(d, s)
        print(f"turnstile {d}: {'OK len=' + str(len(tok)) if tok else 'FAILED'}")

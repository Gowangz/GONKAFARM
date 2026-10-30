"""GonkaRouter API client — daftar, verify, ambil API key.

Alur terbukti (live probe 2026-10-03):
  POST /auth/email/send   {email, channel:"gonka"}            -> {success, expires_in:600, resend_after:60}
  POST /auth/email/verify {email, channel:"gonka", code}      -> {token, user:{id,email}, expires_in:604800}
  GET  /api/me            Authorization: Bearer <token>       -> {balance:{USDT:"20"}, usage, user}
  GET  /api/keys          Authorization: Bearer <token>       -> {items:[{id, key_preview, is_default, name}]}
  POST /api/keys/<id>/reveal                                 -> {id, key:"sk-xxxx...", name}
  GET  /api/pricing                                         -> model list (no auth)

Bonus 20 USDT otomatis untuk user baru (balance.USDT == "20" di /api/me).
Tidak ada turnstile di /auth/email/send untuk domain nodexdigital.web.id.
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request

from config import (CHANNEL, GONKA_API_BASE, LOG_FILE, PROXY, REQUEST_TIMEOUT,
                    RETRY_BACKOFF, RETRY_MAX, TURNSTILE_SITEKEY)
from solver import turnstile

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Proxy 8888 adalah HTTP CONNECT dengan sertifikat self-signed (MITM inspect).
# Tanpa ini koneksi gagal dengan CERTIFICATE_VERIFY_FAILED.
_INSECURE = ssl.create_default_context()
_INSECURE.check_hostname = False
_INSECURE.verify_mode = ssl.CERT_NONE


def _opener(use_proxy: bool, proxy: str | None = None):
    handlers = [urllib.request.HTTPSHandler(context=_INSECURE)]
    if use_proxy:
        handlers.append(urllib.request.ProxyHandler(
            {"http": proxy or PROXY, "https": proxy or PROXY}))
    return urllib.request.build_opener(*handlers)


class GonkaClient:
    """Satu client = satu channel (direct atau proxy)."""

    def __init__(self, use_proxy: bool = False, proxy: str | None = None) -> None:
        self.use_proxy = use_proxy
        self.token = ""
        self.opener = _opener(use_proxy, proxy)
        self.proxy = proxy

    # ── internal ────────────────────────────────────────────────

    def _req(self, method: str, path: str, body: dict | None = None,
             auth: bool = False, timeout: int = REQUEST_TIMEOUT,
             retry: int = RETRY_MAX) -> dict:
        url = f"{GONKA_API_BASE}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://gonkarouter.io",
            "Referer": "https://gonkarouter.io/",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        last = None
        for attempt in range(retry):
            # proxy rotate: setiap koneksi = IP baru. Bangun ulang opener agar
            # retry tidak menempel pada IP yang sama yang kena 403/429.
            if attempt > 0 and self.use_proxy:
                self.opener = _opener(True, self.proxy)
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with self.opener.open(req, timeout=timeout) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                raw = e.read()
                # proxy sering kembali 403 pada IP exit tertentu; IP baru
                # di percobaan berikutnya biasanya langsung lolos.
                if e.code in (429, 502, 503, 504) or (self.use_proxy and e.code == 403):
                    last = f"HTTP {e.code}"
                    time.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                try:
                    return json.loads(raw)
                except Exception:
                    return {"error": {"code": f"http_{e.code}", "message": raw[:200].decode("utf-8", "replace")}}
            except Exception as e:
                # SSL EOF sporadik dari proxy 8888 -> retry
                last = str(e)[:120]
                time.sleep(RETRY_BACKOFF * (attempt + 1))
        return {"error": {"code": "retry_exhausted", "message": str(last)}}

    # ── public ──────────────────────────────────────────────────

    def send_otp(self, email: str) -> dict:
        body = {"email": email, "channel": CHANNEL}
        tok = turnstile("api.gonkarouter.io", TURNSTILE_SITEKEY)
        if tok:
            body["turnstile_token"] = tok
        return self._req("POST", "/auth/email/send", body=body)

    def verify_otp(self, email: str, code: str) -> dict:
        r = self._req("POST", "/auth/email/verify",
                      body={"email": email, "channel": CHANNEL, "code": code})
        if r.get("token"):
            self.token = r["token"]
        return r

    def me(self) -> dict:
        return self._req("GET", "/api/me", auth=True)

    def keys(self) -> dict:
        return self._req("GET", "/api/keys", auth=True)

    def reveal_key(self, key_id) -> dict:
        return self._req("POST", f"/api/keys/{key_id}/reveal", auth=True)

    # ── high level ─────────────────────────────────────────────

    def signup(self, email: str, get_code, otp_timeout: int = 180) -> dict | None:
        """Daftar 1 akun. get_code(local_part) -> OTP string.

        Return {token, user_id, api_key, balance} atau None jika gagal.
        """
        local = email.split("@", 1)[0]
        r = self.send_otp(email)
        if not r.get("success"):
            log(f"[send_otp] gagal: {r}")
            return None
        code = get_code(local)
        if not code:
            log(f"[otp] tidak diterima untuk {email}")
            return None
        r = self.verify_otp(email, code)
        if not r.get("token"):
            log(f"[verify] gagal: {r}")
            return None
        self.token = r["token"]
        uid = (r.get("user") or {}).get("id")

        me = self.me()
        balance = (me.get("balance") or {}).get("USDT", "?")

        keys = self.keys()
        items = keys.get("items") or []
        if not items:
            log(f"[keys] kosong untuk {email}")
            return None
        kid = items[0]["id"]
        rev = self.reveal_key(kid)
        api_key = rev.get("key", "")
        if not api_key or "..." in api_key:
            log(f"[reveal] key masked/kosong: {rev}")
            return None

        return {
            "token": self.token, "user_id": uid, "balance": balance,
            "key_id": kid, "api_key": api_key,
        }

    # ── aktivasi first-call bonus ───────────────────────────────
    def activate_bonus(self, api_key: str | None = None) -> dict:
        """Lakukan 1 API call pertama untuk meng-klaim 'first call bonus'.

        Bonus GonkaRouter (10M token / $20 via halaman promo) biasanya hanya
        dilepas setelah akun menuntaskan 1 real chat call. Fungsi ini memanggil
        /v1/chat/completions via proxy Oxylabs (header browser penuh, hindari
        blokir Cloudflare 1010), lalu cek ulang /api/me untuk saldo baru.

        Return {"called": bool, "balance_before", "balance_after", "error"}.
        """
        key = api_key or self.token
        bb = self._balance(key)          # dict {usdt, bonus_tokens, remaining_tokens}
        balance_before = bb["usdt"]
        tokens_before = bb["remaining_tokens"]
        headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://gonkarouter.io",
            "Referer": "https://gonkarouter.io/",
            "Authorization": f"Bearer {key}",
        }
        payload = {
            "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        }
        req = urllib.request.Request(
            f"{GONKA_API_BASE}/v1/chat/completions",
            data=json.dumps(payload).encode(), headers=headers, method="POST")
        called, err = False, None
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read()
                d = json.loads(raw) if raw else {}
                called = "choices" in d or "usage" in d or bool(d)
                err = None
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:160]}"
        except Exception as e:
            err = str(e)[:160]
        time.sleep(1.5)
        ba = self._balance(key)
        balance_after = ba["usdt"]
        tokens_after  = ba["remaining_tokens"]
        return {"called": called, "balance_before": balance_before,
                "balance_after": balance_after,
                "tokens_before": tokens_before, "tokens_after": tokens_after,
                "error": err}

    def _balance(self, key: str | None = None) -> dict:
        """Query /api/me. Return {usdt, bonus_tokens, remaining_tokens}."""
        bearer = key or self.token or ""
        if not bearer:
            return {"usdt": "?", "bonus_tokens": "?", "remaining_tokens": "?"}
        req = urllib.request.Request(
            f"{GONKA_API_BASE}/api/me",
            headers={"Authorization": f"Bearer {bearer}",
                     "User-Agent": UA, "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=30) as r:
                d = json.loads(r.read())
                return {
                    "usdt": str((d.get("balance") or {}).get("USDT", "?")),
                    "bonus_tokens": (d.get("bonus_tokens") or "?"),
                    "remaining_tokens": (d.get("remaining_tokens") or "?"),
                }
        except Exception:
            return {"usdt": "?", "bonus_tokens": "?", "remaining_tokens": "?"}


def log(msg: str) -> None:
    """Cetak ke stdout DAN tulis ke logs/gonkafarm.log (append, buat jika belum ada)."""
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass  # logging tidak boleh membunuh proses utama

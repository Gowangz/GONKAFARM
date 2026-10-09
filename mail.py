"""NodexClient mail worker — OTP inbox retrieval.

Worker: mail.nodexdigital.web.id (NodexClient / CFMAIL)
Inbox bersifat session-scoped: create & poll harus memakai session id yang sama.
Catch-all *@nodexdigital.web.id aktif, namun inbox hanya muncul setelah dibuat
atau setelah email pertama masuk.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://mail.nodexdigital.web.id"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

OTP_RE = re.compile(r"code\s+is\s+([A-Z0-9]{6})\b", re.IGNORECASE)


def _parse_ts(s: str) -> float:
    """Parse 'YYYY-MM-DD HH:MM:SS' (UTC, worker CF) ke epoch. 0 jika gagal."""
    if not s:
        return 0.0
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0


class MailClient:
    """Satu session = satu kumpulan inbox.

    Satu instance = satu thread (satu worker). Tidak ada lock: session-id dan
    inbox pointer tidak pernah diakses lintas worker, karena setiap worker
    memakai local part-nya sendiri.
    """

    def __init__(self) -> None:
        self.session_id = ""
        self._inbox: str | None = None
        self._seen: dict[str, set[str]] = {}

    # ── internal ────────────────────────────────────────────────

    def _req(self, method: str, path: str, body: dict | None = None,
             timeout: int = 30, retry: int = 3) -> dict:
        url = f"{BASE}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"User-Agent": UA, "Accept": "application/json"}
        if self.session_id:
            headers["x-session-id"] = self.session_id
        if body is not None:
            headers["Content-Type"] = "application/json"

        last: Exception | None = None
        for attempt in range(retry):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                # 404 inbox belum ada / body kosong -> bukan error fatal
                if e.code == 404:
                    return {}
                last = e
            except Exception as e:
                last = e
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"mail {method} {path} failed: {last}")

    # ── public ──────────────────────────────────────────────────

    def new_session(self) -> str:
        self.session_id = str(self._req("GET", "/api/session", retry=2).get("sessionId", ""))
        if not self.session_id:
            raise RuntimeError("mail: sessionId kosong")
        return self.session_id

    def create_inbox(self, local_part: str) -> str:
        """Buat inbox untuk local_part. Idempoten (sudah ada = no-op)."""
        if not self.session_id:
            self.new_session()
        self._req("POST", "/api/inboxes",
                  body={"localPart": local_part, "domain": "nodexdigital.web.id"})
        addr = f"{local_part}@nodexdigital.web.id"
        self._inbox = addr
        return addr

    def _messages(self, inbox: str) -> list[dict]:
        q = urllib.parse.quote(inbox)
        out = self._req("GET", f"/api/inboxes/{q}/messages")
        return out if isinstance(out, list) else []

    def wait_otp(self, local_part: str, timeout_s: int = 180,
                 poll_interval: int = 3, min_wait_s: float = 0.0) -> str | None:
        """Poll inbox untuk OTP GonkaRouter. Return kode atau None jika timeout.

        min_wait_s: jika >0, abaikan pesan yang diterima sebelum timestamp ini.
                    Dipakai agar retry tidak membaca kode lama yang sudah hangus.
        """
        if not self.session_id:
            self.new_session()
        inbox = f"{local_part}@nodexdigital.web.id"
        cutoff = time.time() - min_wait_s if min_wait_s > 0 else 0.0

        deadline = time.monotonic() + timeout_s
        seen_ids = self._seen.setdefault(inbox, set())
        while time.monotonic() < deadline:
            msgs = self._messages(inbox)
            for msg in msgs:
                mid = msg.get("id", "")
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                # Lewati email yang lebih lama dari cutoff (OTP sebelum retry)
                ts = _parse_ts(msg.get("received_at", ""))
                if ts and ts < cutoff:
                    continue
                body = msg.get("body", "") or ""
                subj = msg.get("subject", "") or ""
                frm = (msg.get("from_address", "") or "").lower()
                if "gonka" not in frm and "gonka" not in subj.lower():
                    continue
                m = OTP_RE.search(body)
                if m:
                    return m.group(1).upper()
            time.sleep(poll_interval)
        return None


if __name__ == "__main__":
    import sys

    mc = MailClient()
    mc.new_session()
    if len(sys.argv) > 1:
        lp = sys.argv[1]
        print("inbox:", mc.create_inbox(lp))
        print("otp:", mc.wait_otp(lp, timeout_s=60))
    else:
        print("usage: mail.py <local_part>")

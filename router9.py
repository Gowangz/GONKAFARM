"""Sinkron API key GonkaRouter ke 9router via HTTP API resmi.

Sebelumnya menulis langsung ke data.sqlite — tapi 9router yang sedang jalan
memakai cache ORM di memori, jadi insert langsung tidak muncul di dashboard
sampai service di-restart.

Sekarang pakai API dashboard yang sama:
  POST   /api/auth/login       -> cookie auth_token
  GET    /api/providers        -> daftar connection (apiKey di-mask)
  POST   /api/providers        -> tambah {provider, apiKey, name}
  DELETE /api/providers/{id}   -> hapus connection

Dipakai format yang sama dengan key manual yang sudah ada:
  baseUrl https://api.gonkarouter.io/v1, nodeName GONKA, prefix gk.

Duplikasi dicegah 2 lapis:
  1. GET /api/providers cek nama yang sama (nama = hash dari key)
  2. .router9_state.json mencatat key terkirim — survive restart 9router
     maupun restart script.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:20128"
# provider id stabil — sama dengan yang dipakai dashboard untuk GonkaRouter.
# Ambil dari GET /api/providers milik "Key 1" manual, supaya key hasil script
# bergabung dengan provider yang sudah ada, bukan bikin kelompok baru.
PROVIDER = "openai-compatible-chat-d8f0def1-8be1-4deb-b58f-241f3cb45ef6"

_HERE = Path(__file__).resolve().parent
_ENV_PATH = _HERE / ".env"
_LOG_PATH = _HERE / "logs" / "router9.log"
_STATE_PATH = _HERE / ".router9_state.json"


def _log(msg: str) -> None:
    line = f"[router9] {msg}"
    print(line, flush=True)
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_env() -> dict:
    """Baca .env (format KEY=value). Tidak butuh python-dotenv."""
    out = dict(os.environ)
    if _ENV_PATH.is_file():
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class Router9API:
    """Client HTTP API 9router."""

    def __init__(self, password: str | None = None):
        env = _load_env()
        self.password = password or env.get("ROUTER9_PASSWORD", "")
        self.cookie: str | None = None

    def login(self) -> bool:
        if not self.password:
            _log("ROUTER9_PASSWORD kosong — baca .env")
            return False
        req = urllib.request.Request(
            f"{BASE_URL}/api/auth/login",
            data=json.dumps({"password": self.password}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                ok = json.loads(r.read()).get("success", False)
                for c in (r.headers.get_all("Set-Cookie") or []):
                    if c.startswith("auth_token="):
                        self.cookie = c.split(";")[0]
                return ok and self.cookie is not None
        except Exception as e:
            _log(f"login 9router gagal: {e}")
            return False

    def _req(self, path: str, data: bytes | None = None,
             method: str = "GET") -> dict:
        if not self.cookie:
            raise RuntimeError("belum login")
        headers = {"Cookie": self.cookie}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{BASE_URL}{path}", data=data,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            return json.loads(body) if body else {}

    def list_connections(self) -> list[dict]:
        """Daftar connection. Catatan: API mem-mask apiKey."""
        return self._req("/api/providers").get("connections", [])

    def gonka_connections(self) -> list[dict]:
        """Connection milik provider GonkaRouter."""
        return [c for c in self.list_connections()
                if c.get("provider") == PROVIDER]

    def add(self, apikey: str, name: str) -> dict:
        """Tambah satu key. Return response API."""
        return self._req("/api/providers",
                         data=json.dumps(
                             {"provider": PROVIDER, "apiKey": apikey,
                              "name": name}).encode(),
                         method="POST")

    def delete(self, conn_id: str) -> dict:
        return self._req(f"/api/providers/{conn_id}", method="DELETE")


# ── state: key yang sudah dikirim ────────────────────────────────


def _load_sent() -> set[str]:
    if _STATE_PATH.is_file():
        try:
            return set(json.loads(_STATE_PATH.read_text()).get("sent", []))
        except Exception:
            pass
    return set()


def _save_sent(sent: set[str]) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps({"sent": sorted(sent)}))
    except Exception as e:
        _log(f"gagal simpan state: {e}")


def key_name(apikey: str, prefix: str = "GONKA") -> str:
    """Nama unik dari hash key. Anti-collision antar instance."""
    return f"{prefix} {hashlib.sha256(apikey.encode()).hexdigest()[:8]}"


def reconcile_to_9router(keys: list[str], prefix: str = "GONKA") -> dict:
    """Tambah key baru ke 9router via API. Add-only — tidak pernah hapus.

    Return {"added": n, "skipped": n, "failed": n}
    """
    if not keys:
        return {"added": 0, "skipped": 0, "failed": 0}

    api = Router9API()
    if not api.login():
        _log("tidak bisa login ke 9router — sinkron dibatalkan")
        return {"added": 0, "skipped": 0, "failed": len(keys)}

    try:
        existing_names = {c["name"] for c in api.gonka_connections()}
    except Exception as e:
        _log(f"gagal ambil daftar provider: {e}")
        return {"added": 0, "skipped": 0, "failed": len(keys)}

    sent = _load_sent()
    added = skipped = failed = 0

    for k in keys:
        if not k:
            continue
        name = key_name(k, prefix)
        if name in existing_names or k in sent:
            skipped += 1
            continue
        try:
            api.add(k, name)
            sent.add(k)
            added += 1
            _log(f"+ {name}")
        except urllib.error.HTTPError as e:
            _log(f"gagal tambah {name}: HTTP {e.code} "
                 f"{e.read().decode()[:120]}")
            failed += 1
        except Exception as e:
            _log(f"gagal tambah {name}: {e}")
            failed += 1

    _save_sent(sent)
    return {"added": added, "skipped": skipped, "failed": failed}


def list_gonka() -> list[str]:
    """Daftar id connection GonkaRouter di 9router.

    API mem-mask apiKey, jadi kembalikan id — dipakai hanya untuk
    menampilkan jumlah di menu, bukan untuk cek duplikasi.
    """
    api = Router9API()
    if not api.login():
        return []
    try:
        return [c["id"] for c in api.gonka_connections()]
    except Exception:
        return []


if __name__ == "__main__":
    keys = [l.strip() for l in open("Apikey.txt") if l.strip()]
    print(f"Apikey.txt: {len(keys)} key")
    r = reconcile_to_9router(keys)
    print(f"+{r['added']} baru, {r['skipped']} sudah ada, "
          f"{r['failed']} gagal | total 9router: {len(list_gonka())}")

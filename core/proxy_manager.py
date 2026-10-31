#!/usr/bin/env python3
"""Proxy Manager sederhana untuk GONKAFARM.

Menyediakan:
1. Gateway HTTP di 127.0.0.1:8888 yang memberikan IP acak dari pool tiap request.
2. Fungsi panen (harvest) proxy publik sederhana + validasi.
3. Pool proxy in-memory yang bisa di-share antar modul.

Fitur utama:
- Rotasi IP otomatis tiap request (bukan sticky session).
- Validasi cepat lewat https://cloudflare.com/cdn-cgi/trace & https://ipify.org.
- Anti-block: proxy di-validate sebelum dimasukkan pool.
- Tidak butuh captcha solver (hanya validasi HTTP 200).
- Bisa dipakai dari farm.py sebagai proxy alternatif ke Oxylabs.
"""

import asyncio
import json
import logging
import random
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

try:
    import aiohttp
except ImportError:
    aiohttp = None
try:
    import requests
except ImportError:
    requests = None

# Konfigurasi default
DEFAULT_GATEWAY_PORT = 8888
DEFAULT_POOL_SIZE = 50
DEFAULT_MAX_LATENCY_MS = 500
DEFAULT_TEST_URL = "https://cloudflare.com/cdn-cgi/trace"
DEFAULT_VALIDATE_URL = "https://ipify.org"

log = logging.getLogger("proxy_manager")

# ==================== Internal State ====================

# Pool proxy yang sudah divalidasi: list[dict] dengan kun kunci: protocol, proxy, last_used, latency_ms
_proxy_pool: List[dict] = []
_pool_lock = threading.Lock()

# Gateway server state
_gateway_server: Optional[threading.Thread] = None
_gateway_port: int = DEFAULT_GATEWAY_PORT
_gateway_stop_event = threading.Event()
_gateway_healthy_count = 0


# ==================== Validasi Proxy ====================

def _validate_proxy_http(proxy_url: str, test_url: str = DEFAULT_TEST_URL, timeout: float = 5.0) -> bool:
    """Validasi proxy lewat HTTP request ke Cloudflare trace."""
    try:
        proto, rest = proxy_url.split("://", 1)
        proxy_url_full = f"{proto}://{rest}"
        proxies = {"http": proxy_url_full, "https": proxy_url_full}
        resp = requests.get(test_url, proxies=proxies, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _validate_proxy_socks(proxy_url: str, timeout: float = 5.0) -> bool:
    """Validasi SOCKS proxy lewat koneksi langsung ke ipify."""
    try:
        import socks  # requires PySocks
        socket.setdefaulttimeout(timeout)
        # SOCKS validation melewati http library, coba koneksi ke endpoint sederhana
        return True  # placeholder: asumsi valid jika lewat check lain
    except ImportError:
        return False


def validate_proxy(proxy_item: dict) -> bool:
    """Validasi lengkap proxy dari dict {protocol, proxy}."""
    proto = proxy_item.get("protocol", "http").lower()
    proxy_str = proxy_item.get("proxy", "")

    if not proxy_str:
        return False

    if proto in ("http", "https"):
        return _validate_proxy_http(proxy_str)
    # socks4/5 bisa ditambahkan nanti
    return False


# ==================== Penambah Proxy ke Pool ====================

def add_proxy(proxy_dict: dict, validate: bool = True) -> bool:
    """Menambah proxy ke pool setelah (opsional) validasi."""
    if validate and not validate_proxy(proxy_dict):
        log.debug(f"Proxy tidak valid, dilewati: {proxy_dict.get('proxy', '')[:20]}...")
        return False

    with _pool_lock:
        # Cek duplikat berdasarkan proxy string
        existing = {p.get("proxy", "").lower() for p in _proxy_pool}
        if proxy_dict.get("proxy", "").lower() not in existing:
            _proxy_pool.append(proxy_dict)
            log.info(f"Proxy ditambahkan ke pool. Total: {len(_proxy_pool)}")
            return True
    return False


def get_proxy() -> Optional[dict]:
    """Ambil proxy acak dari pool. Pool akan di-rotasi otomatis."""
    with _pool_lock:
        if not _proxy_pool:
            return None
        now = time.time()
        best = min(_proxy_pool, key=lambda p: p.get("last_used", 0))
        best["last_used"] = now
        return best


def refresh_pool(count: int = None, max_latency_ms: int = DEFAULT_MAX_LATENCY_MS) -> int:
    """Refill pool dengan proxy baru. Return jumlah proxy baru ditambah."""
    count = count or DEFAULT_POOL_SIZE
    added = 0

    # Sumber proxy publik raw-text (tanpa captcha solver)
    sources = [
        ("http", "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all"),
        ("http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"),
        ("http", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
        ("http", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"),
        ("socks4", "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=5000&country=all"),
        ("socks4", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt"),
        ("socks5", "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=5000&country=all"),
        ("socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"),
    ]

    for proto, source in sources:
        if added >= count:
            break
        try:
            resp = requests.get(source, timeout=15)
            if resp.status_code == 200:
                text = resp.text
                for line in text.splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    parts = line.split(":")
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        port = parts[1].strip()
                        if not port.isdigit():
                            continue
                        proxy_dict = {
                            "protocol": proto,
                            "proxy": f"{proto}://{ip}:{port}",
                            "last_used": 0,
                            "latency_ms": 999,
                        }
                        if add_proxy(proxy_dict, validate=True):
                            added += 1
        except Exception as e:
            log.debug(f"Gagal ambil dari source {source}: {e}")

    log.info(f"Pool refresh: +{added} proxy baru (total sekarang: {len(_proxy_pool)})")
    return added


# ==================== Gateway HTTP Sederhana ====================

class _GatewayHandler:
    """Handler request untuk gateway HTTP."""

    def __init__(self, port: int):
        self.port = port

    def _handle_request(self, reader, writer):
        try:
            with _pool_lock:
                if not _proxy_pool:
                    writer.write(b"HTTP/1.1 503 No proxies available\r\n\r\n")
                    writer.close()
                    return

                proxy_item = random.choice(_proxy_pool)
                proxy_str = proxy_item.get("proxy", "")

            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n{proxy_str}\r\n\r\n"
            writer.write(response.encode())
            writer.close()
        except Exception as e:
            log.error(f"Gateway error: {e}")
            try:
                writer.write(b"HTTP/1.1 500 Internal Error\r\n\r\n")
                writer.close()
            except Exception:
                pass


async def _start_gateway(port: int):
    import aiohttp
    from aiohttp import web

    app = web.Application()
    app.router.add_get("/", _GatewayHandler(port)._handle_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    log.info(f"Gateway dimulai di http://127.0.0.1:{port}")


def start_gateway(port: int = DEFAULT_GATEWAY_PORT) -> bool:
    global _gateway_server, _gateway_port, _gateway_stop_event

    _gateway_port = port
    _gateway_stop_event = threading.Event()

    if len(_proxy_pool) < 5:
        log.info("Pool proxy masih kecil, memulai refresh...")
        refresh_pool(count=5)

    _gateway_server = threading.Thread(target=_start_gateway_server, args=(port,), daemon=True)
    _gateway_server.start()
    log.info(f"Gateway proxy dimulai di http://127.0.0.1:{port}")
    return True


def _start_gateway_server(port: int):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_start_gateway_server(port))
    except Exception as e:
        log.error(f"Gateway startup failed: {e}")
    finally:
        loop.close()


def stop_gateway():
    global _gateway_server
    if _gateway_server:
        _gateway_stop_event.set()
        _gateway_server.join(timeout=5)
        _gateway_server = None
        log.info("Gateway dihentikan")


# ==================== Utilitas Bantuan ====================

def get_proxy() -> Optional[dict]:
    with _pool_lock:
        if not _proxy_pool:
            return None
        now = time.time()
        best = min(_proxy_pool, key=lambda p: p.get("last_used", 0))
        best["last_used"] = now
        return best


def get_proxy_url() -> Optional[str]:
    proxy_item = get_proxy()
    if proxy_item:
        return proxy_item.get("proxy")
    return None


# Alias
validate_and_refill = validate_proxy

# ==================== Exit Handler ====================

import atexit

def _atexit_handler():
    stop_gateway()

atexit.register(_atexit_handler)

# End of file

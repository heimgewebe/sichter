#!/usr/bin/env python3
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from urllib.parse import urljoin, urlparse
import urllib.request
import urllib.error

DEFAULT_BASE = os.environ.get("SICHTER_API_BASE", "http://127.0.0.1:5055")

def _norm_base(base: str) -> str:
    if not base.startswith(("http://", "https://")):
        return "http://" + base
    return base

async def _ws_run(url: str, limit: int, timeout: float) -> int:
    """
    Versucht, über websockets (oder websocket-client) zu verbinden und
    genau 'limit' Nachrichten zu lesen. Gibt 0 bei Erfolg zurück, sonst !=0.
    """
    # 1) asyncio websockets
    try:
        import websockets  # type: ignore
    except Exception:
        websockets = None

    if websockets is not None:
        # http(s) -> ws(s)
        parsed = urlparse(url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = parsed._replace(scheme=ws_scheme).geturl()
        print(f"[ws-selftest] Trying asyncio websockets -> {ws_url}")
        try:
            async with websockets.connect(ws_url, close_timeout=1.0) as ws:
                # Begrüßung kommt evtl. als Replay
                count = 0
                start = time.time()
                while count < limit and (time.time() - start) < timeout:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    print(msg if isinstance(msg, str) else str(msg))
                    count += 1
                if count >= limit:
                    print(f"[ws-selftest] ✅ received {count} messages")
                    return 0
                print(f"[ws-selftest] ⚠️ timeout after {int(time.time()-start)}s, received {count}/{limit}")
                return 2
        except Exception as e:
            print(f"[ws-selftest] websockets connect failed: {e}")
            # fall-through to other clients

    # 2) websocket-client (threaded)
    try:
        import websocket  # type: ignore
    except Exception:
        websocket = None
    if websocket is not None:
        import threading
        parsed = urlparse(url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = parsed._replace(scheme=ws_scheme).geturl()
        print(f"[ws-selftest] Trying websocket-client -> {ws_url}")
        count = 0
        def on_message(_, message):
            nonlocal count
            print(message)
            count += 1
        wsapp = websocket.WebSocketApp(ws_url, on_message=on_message)

        # run_forever is blocking, so run it in a thread
        wst = threading.Thread(target=wsapp.run_forever)
        wst.daemon = True
        wst.start()

        t0 = time.time()
        while count < limit and (time.time() - t0) < timeout:
            time.sleep(0.1)

        wsapp.close()

        if count >= limit:
            print(f"[ws-selftest] ✅ received {count} messages")
            return 0

        print(f"[ws-selftest] ⚠️ timeout, received {count}/{limit}")
        return 2

    print("[ws-selftest] No WebSocket client installed (websockets or websocket-client)")
    return 3

def _http_fallback(base: str, limit: int) -> int:
    """
    Fallback: Polling gegen /events/recent (HTTP). Dient nur als Erreichbarkeitsprobe.
    """
    url = urljoin(base, f"/events/recent?n={limit}")
    print(f"[ws-selftest] Fallback HTTP -> {url}")
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = resp.read().decode("utf-8", "replace")
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict) and "events" in obj:
                events = obj.get("events") or []
                for e in events:
                    line = e.get("line") if isinstance(e, dict) else None
                    if line:
                        print(line)
                print(f"[ws-selftest] ✅ HTTP fallback received {len(events)} events")
                return 0 if events else 4
            print("[ws-selftest] Unexpected HTTP payload")
            return 5
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[ws-selftest] HTTP error: {e}")
        return 6

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Sichter WebSocket self-test")
    p.add_argument("--base", default=DEFAULT_BASE, help="API base URL (default: %(default)s)")
    p.add_argument("--replay", type=int, default=10, help="Replay count for WS (default: %(default)s)")
    p.add_argument("--timeout", type=float, default=20.0, help="Overall time budget for WS in seconds (default: %(default)s)")
    args = p.parse_args(argv)

    base = _norm_base(args.base)
    ws_url = urljoin(base, f"/events/stream?replay={max(1,args.replay)}&heartbeat=10")

    # Try WS first
    try:
        rc = asyncio.run(_ws_run(ws_url, limit=max(1,args.replay), timeout=max(3.0, args.timeout)))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"[ws-selftest] unexpected error: {e}")
        rc = 9

    if rc == 0:
        return 0
    # Soft fallback to HTTP /events/recent
    return _http_fallback(base, limit=max(1,args.replay))

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Run the browser RPG UI with a standard-library local web server."""

from __future__ import annotations

import sys as _sys
_sys.dont_write_bytecode = True  # V34: prevent stale .pyc cache

import argparse
import json
import mimetypes
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
STATIC_ROOT = PROJECT_ROOT / "web" / "static"
sys.path.insert(0, str(TOOLS_DIR))

import web_api  # noqa: E402


class GameServer:
    def __init__(self) -> None:
        self.current_root = PROJECT_ROOT.resolve()


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def make_handler(server_state: GameServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[web] {self.address_string()} - {fmt % args}")

        def do_GET(self) -> None:
            try:
                self.route_get()
            except Exception as exc:
                json_response(self, 500, {"error": str(exc)})

        def do_POST(self) -> None:
            try:
                self.route_post()
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            except Exception as exc:
                json_response(self, 500, {"error": str(exc)})

        def route_get(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/campaigns":
                json_response(self, 200, {"campaigns": web_api.list_campaigns()})
                return
            if parsed.path == "/api/state":
                query = parse_qs(parsed.query)
                if "campaign" in query:
                    server_state.current_root = web_api.safe_campaign_path(query["campaign"][0])
                json_response(self, 200, web_api.visible_state(server_state.current_root))
                return
            if parsed.path == "/api/logs":
                json_response(self, 200, {"logs": web_api.recent_logs(server_state.current_root)})
                return
            if parsed.path == "/api/config":
                json_response(
                    self,
                    200,
                    {
                        "project_root": str(PROJECT_ROOT),
                        "current_campaign": web_api.campaign_key(server_state.current_root),
                        "api": web_api.api_status(server_state.current_root),
                    },
                )
                return
            self.serve_static(parsed.path)

        def route_post(self) -> None:
            parsed = urlparse(self.path)
            body = read_json_body(self)
            if parsed.path == "/api/campaigns/new":
                result = web_api.create_campaign(
                    str(body.get("theme", "")),
                    force=bool(body.get("force", True)),
                )
                server_state.current_root = web_api.safe_campaign_path(result["campaign"]["id"])
                json_response(self, 200, result)
                return
            if parsed.path == "/api/campaigns/select":
                server_state.current_root = web_api.safe_campaign_path(str(body.get("campaign", ".")))
                json_response(self, 200, web_api.visible_state(server_state.current_root))
                return
            if parsed.path == "/api/campaigns/delete":
                result = web_api.delete_campaign(str(body.get("campaign", "")))
                server_state.current_root = web_api.safe_campaign_path(result["next_campaign"])
                result["state"] = web_api.visible_state(server_state.current_root)
                json_response(self, 200, result)
                return
            if parsed.path == "/api/turn":
                if body.get("campaign"):
                    server_state.current_root = web_api.safe_campaign_path(str(body["campaign"]))
                elapsed_value = body.get("elapsed_minutes")
                elapsed_minutes = None if elapsed_value in (None, "", "auto") else int(elapsed_value)
                result = web_api.run_turn(
                    server_state.current_root,
                    str(body.get("action", "")),
                    elapsed_minutes=elapsed_minutes,
                    memory_limit=int(body.get("memory_limit", 8)),
                )
                json_response(self, 200, result)
                return
            if parsed.path == "/api/roll":
                json_response(self, 200, web_api.roll_dice(str(body.get("expression", "1d20"))))
                return
            if parsed.path == "/api/validate":
                if body.get("campaign"):
                    server_state.current_root = web_api.safe_campaign_path(str(body["campaign"]))
                json_response(self, 200, web_api.validate(server_state.current_root))
                return
            if parsed.path == "/api/obsidian/export":
                if body.get("campaign"):
                    server_state.current_root = web_api.safe_campaign_path(str(body["campaign"]))
                json_response(self, 200, web_api.export_obsidian(server_state.current_root))
                return
            json_response(self, 404, {"error": "not found"})

        def serve_static(self, request_path: str) -> None:
            relative = request_path.lstrip("/") or "index.html"
            path = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT.resolve() not in path.parents and path != STATIC_ROOT.resolve():
                json_response(self, 403, {"error": "forbidden"})
                return
            if path.is_dir():
                path = path / "index.html"
            if not path.exists():
                path = STATIC_ROOT / "index.html"
            content = path.read_bytes()
            mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if path.suffix in {".html", ".css", ".js"}:
                mime += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Paotuan browser RPG UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()

    state = GameServer()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    url = f"http://{args.host}:{args.port}/"
    print(f"Paotuan RPG UI running at {url}")
    print("Mode: api")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Paotuan RPG UI.")


if __name__ == "__main__":
    main()

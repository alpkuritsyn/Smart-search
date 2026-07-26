#!/usr/bin/env python3
"""
HTTP Backend Server for Smart-search V1.
Serves GET /api/search?q=... and web/demo/ static files.
"""
import json
import mimetypes
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure entity resolver mode defaults to apply for full ML entity resolution
os.environ["SMART_SEARCH_ENTITY_RESOLVER_MODE"] = os.environ.get("SMART_SEARCH_ENTITY_RESOLVER_MODE") or "apply"
if os.environ["SMART_SEARCH_ENTITY_RESOLVER_MODE"] == "off":
    os.environ["SMART_SEARCH_ENTITY_RESOLVER_MODE"] = "apply"
os.environ["SMART_SEARCH_ENTITY_RESOLVER_POLICY"] = "top1"

from src.search.engine import get_entity_resolver_health, search_catalog_v1

WEB_DIR = BASE_DIR / "web" / "demo"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

class SmartSearchHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet standard HTTP logging
        pass

    def send_json_response(self, data: dict, status: int = 200) -> None:
        def sanitize(obj):
            if isinstance(obj, (set, frozenset)):
                return [sanitize(x) for x in obj]
            if isinstance(obj, dict):
                return {str(k): sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [sanitize(v) for v in obj]
            return obj

        try:
            body = json.dumps(sanitize(data), ensure_ascii=False, default=str).encode("utf-8")
        except Exception:
            body = json.dumps(str(data), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        raw_path = self.path
        try:
            raw_path_bytes = raw_path.encode("iso-8859-1")
            raw_path = raw_path_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass
        unquoted_path = urllib.parse.unquote(raw_path, encoding="utf-8")
        parsed_url = urllib.parse.urlparse(unquoted_path)
        path = parsed_url.path

        # Support /Smart-search prefix
        if path.startswith("/Smart-search"):
            path = path[len("/Smart-search"):]
            if not path:
                path = "/"

        if path == "/api/search":
            query_params = urllib.parse.parse_qs(parsed_url.query)
            query_str = query_params.get("q", [""])[0]
            legacy_flag = query_params.get("legacy", ["0"])[0] == "1"
            try:
                res = search_catalog_v1(query_str, use_legacy_force=legacy_flag)
                self.send_json_response(res, status=200)
            except Exception as e:
                self.send_json_response({"error": str(e)}, status=500)
            return

        if path == "/api/health":
            self.send_json_response({
                "status": "ok",
                "service": "smart-search-v1",
                "entity_resolver": get_entity_resolver_health(),
            }, status=200)
            return

        # Serve static files from WEB_DIR
        rel_path = path.lstrip("/")
        if not rel_path:
            rel_path = "index.html"

        target_file = (WEB_DIR / rel_path).resolve()
        # Security check to prevent directory traversal
        if not str(target_file).startswith(str(WEB_DIR.resolve())):
            self.send_error(403, "Forbidden")
            return

        if target_file.exists() and target_file.is_file():
            mime_type, _ = mimetypes.guess_type(target_file)
            mime_type = mime_type or "application/octet-stream"
            content = target_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type or "json" in mime_type else mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "File Not Found")

def run_server(host=HOST, port=PORT):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, SmartSearchHandler)
    print(f"Smart-search V1 Backend Server running at http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()

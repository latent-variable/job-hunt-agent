#!/usr/bin/env python3
"""
Local dashboard server for the job application agent.

Serves the dashboard HTML and provides API endpoints for reading/writing
the JSON data files.

Usage:
  python tools/serve_dashboard.py [--port 8080]
"""

import argparse
import json
import sys
import webbrowser
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCAN_DIR = DATA_DIR / "scan_results"


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.path = "/dashboard.html"
            return super().do_GET()
        elif path == "/api/applications":
            self._serve_json(DATA_DIR / "applications.json")
        elif path == "/api/companies":
            self._serve_json(DATA_DIR / "companies.json")
        elif path == "/api/scan/latest":
            self._serve_latest_scan()
        elif path == "/api/scans":
            self._serve_scan_list()
        elif path.startswith("/api/scan/"):
            filename = path.split("/api/scan/")[1]
            self._serve_json(SCAN_DIR / filename)
        else:
            return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if path == "/api/applications":
            self._update_json(DATA_DIR / "applications.json", body)
        elif path == "/api/companies":
            self._update_json(DATA_DIR / "companies.json", body)
        else:
            self.send_error(404)

    def _serve_json(self, filepath):
        try:
            with open(filepath) as f:
                data = f.read()
            # Validate JSON before serving
            json.loads(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
        except FileNotFoundError:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "not found"}')
        except json.JSONDecodeError as e:
            # Return empty data if JSON is malformed (e.g., during scan write)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "malformed json", "details": "' + str(e).encode() + b'"')

    def _serve_latest_scan(self):
        if not SCAN_DIR.exists():
            self._serve_json(SCAN_DIR / "nonexistent")
            return
        files = sorted(SCAN_DIR.glob("scan_*.json"), reverse=True)
        if not files:
            self._serve_json(SCAN_DIR / "nonexistent")
            return
        latest = self._select_latest_dashboard_scan(files)
        try:
            with open(latest) as f:
                json.load(f)
            self._serve_json(latest)
        except json.JSONDecodeError:
            for f in files[1:]:
                try:
                    with open(f) as fh:
                        json.load(fh)
                    self._serve_json(f)
                    return
                except json.JSONDecodeError:
                    continue
            self._serve_json(SCAN_DIR / "nonexistent")

    def _serve_scan_list(self):
        if not SCAN_DIR.exists():
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'[]')
            return
        files = sorted(SCAN_DIR.glob("scan_*.json"), reverse=True)
        result = [{"filename": f.name, "modified": f.stat().st_mtime} for f in files]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def _update_json(self, filepath, body):
        try:
            data = json.loads(body)
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _select_latest_dashboard_scan(self, files: list[Path]) -> Path:
        """Prefer the newest full-scope scan for the main dashboard view."""
        for filepath in files:
            if self._infer_scan_scope(filepath) == "all":
                return filepath
        return files[0]

    def _infer_scan_scope(self, filepath: Path) -> str:
        """Infer whether a scan file represents a full dashboard scan or a focused company scan."""
        try:
            with open(filepath) as f:
                data = json.load(f)
        except Exception:
            return "unknown"

        scope = data.get("scan_scope")
        if scope in {"all", "company"}:
            return scope

        if data.get("company_filter"):
            return "company"

        companies_scanned = data.get("companies_scanned")
        if isinstance(companies_scanned, list):
            return "all" if len(companies_scanned) > 1 else "company"

        jobs = data.get("top_results") or []
        companies = {job.get("company") for job in jobs if job.get("company")}
        return "all" if len(companies) > 1 else "company"

    def log_message(self, format, *args):
        # Suppress noisy request logs
        pass


def main():
    parser = argparse.ArgumentParser(description="Job Application Dashboard Server")
    parser.add_argument("--port", "-p", type=int, default=8181)
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    server = HTTPServer(("localhost", args.port), DashboardHandler)
    url = f"http://localhost:{args.port}"
    print(f"Dashboard running at {url}")
    print("Press Ctrl+C to stop")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

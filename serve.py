#!/usr/bin/env python3
"""
serve.py — runs the dashboard locally.

The dashboard fetches data/results.json and data/run_meta.json via the
`fetch()` API, which browsers block on file:// URLs (CORS). This spins up
a plain stdlib HTTP server rooted at dashboard/ and opens it in the
default browser, so double-clicking index.html is never required.

Usage:
    python serve.py                 # serve on http://localhost:8000
    python serve.py --port 5050      # custom port
    python serve.py --no-browser     # don't auto-open a browser tab
"""

import argparse
import http.server
import json
import socketserver
import sys
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs

from engine import upload_ranking

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
ROOT_DIR = Path(__file__).resolve().parent


class RankHandler(http.server.SimpleHTTPRequestHandler):
    def _parse_multipart(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return {}, b""

        boundary = content_type.split("boundary=")[-1]
        if not boundary:
            return {}, b""

        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        parts = raw.split(f"--{boundary}".encode())
        fields = {}
        for part in parts:
            if not part or part in {b"\r\n", b"--\r\n", b"--"}:
                continue
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if b"\r\n\r\n" not in part:
                continue
            header_bytes, body = part.split(b"\r\n\r\n", 1)
            headers = {}
            for line in header_bytes.decode("utf-8", errors="ignore").split("\r\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            if "filename" in headers.get("content-disposition", ""):
                name = headers.get("content-disposition", "").split("name=\"")[1].split("\"")[0]
                filename = headers.get("content-disposition", "").split("filename=\"")[1].split("\"")[0]
                fields[name] = {"filename": filename, "content": body[:-2] if body.endswith(b"\r\n") else body}
            else:
                name = headers.get("content-disposition", "").split("name=\"")[1].split("\"")[0]
                fields[name] = body.decode("utf-8", errors="ignore")
        return fields, raw

    def do_POST(self):
        if self.path != "/upload":
            self.send_error(404, "Not found")
            return

        fields, _ = self._parse_multipart()
        uploaded = fields.get("file")
        mode = fields.get("mode", "lexical")
        if not isinstance(uploaded, dict) or not uploaded.get("filename"):
            self.send_error(400, "No file uploaded")
            return

        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
            tmp.write(uploaded["content"])
            tmp_path = Path(tmp.name)

        try:
            candidates = upload_ranking.load_candidates_from_csv(tmp_path)
            ranked = upload_ranking.rank_candidates(candidates, mode=mode)
            results = []
            for i, item in enumerate(ranked, start=1):
                feats = item["feats"]
                results.append({
                    "rank": i,
                    "candidate_id": item["candidate_id"],
                    "anonymized_name": feats["anonymized_name"],
                    "score": item["score"],
                    "reasoning": item["reasoning"],
                    "current_title": feats["current_title"],
                    "current_company": feats["current_company"],
                    "years_of_experience": feats["years_of_experience"],
                    "location": feats["location"],
                    "country": feats["country"],
                    "matched_concepts": [k.replace("_", " ") for k, v in feats["core_concepts"].items() if v > 0],
                    "nice_to_have_matched": [k.replace("_", " ") for k, v in feats["nice_to_have"].items() if v > 0],
                    "fired_disqualifiers": item["fired_disqualifiers"],
                    "behavioral_modifier": round(feats["behavioral_modifier"], 3),
                    "notice_period_days": feats["notice_period_days"],
                    "willing_to_relocate": feats["willing_to_relocate"],
                    "open_to_work_flag": feats["open_to_work_flag"],
                })
            payload = {"mode": mode, "candidate_count": len(candidates), "results": results[:10]}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        finally:
            tmp_path.unlink(missing_ok=True)

    def do_GET(self):
        if self.path.startswith("/upload"):
            self.send_error(405, "Use POST")
            return
        return super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--browser", action="store_true", help="Open the dashboard in a browser")
    args = parser.parse_args()

    if not (DASHBOARD_DIR / "data" / "results.json").exists():
        print(
            "Warning: dashboard/data/results.json not found yet.\n"
            "Run the ranker first, e.g.:\n"
            "  python rank.py --candidates ./data/candidates.jsonl "
            "--out output/submission.csv --json-out dashboard/data/results.json "
            "--meta-out dashboard/data/run_meta.json\n",
            file=sys.stderr,
        )

    handler = lambda *a, **kw: RankHandler(*a, directory=str(DASHBOARD_DIR), **kw)

    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/index.html"
        print(f"Serving dashboard at {url}  (Ctrl+C to stop)")
        if args.browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()

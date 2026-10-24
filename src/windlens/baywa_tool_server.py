"""Track B: minimal local tool -- upload a wind-data file (+ optional matching power
curve), run WindLens's wind-first single-reference reconstruction against it, and see
the result rendered inside the main WindLens workspace. stdlib-only
(``http.server``); no new dependency.

Run with:  PYTHONPATH=src python3 -m windlens.baywa_tool_server
Then open: http://127.0.0.1:8765/#upload  (the whole workspace -- Overview, Analysis,
Methodology, and Upload & run -- is served from this one process; there is no longer
a separate static server + separate upload tool).

This is a thin HTTP wrapper over ``upload_tool.run_pipeline`` -- all the actual
reconstruction logic is Track A's existing, tested pipeline pieces; this file only
does static-file serving for workspace/, upload parsing, auto-detection vs.
manual-override wiring, and returning the result as JSON for the workspace's own
app.js to render (``/run`` used to render its own plain HTML page; the workspace's
"Upload & run" tab now does that rendering in the shared visual design system).
Binds to 127.0.0.1 only (not 0.0.0.0) -- a local tool, not a public service.

Python 3.13+ removed the stdlib ``cgi`` module, so multipart/form-data is parsed here
by hand (``_parse_multipart``) -- deliberately minimal (splits on the boundary and
reads each part's own headers), not a general MIME parser.
"""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from windlens.insurance_report import generate as generate_insurance_report
from windlens.upload_tool import (
    classify_file_kind,
    describe_uploaded_files,
    load_power_curve,
    load_wind_data_files,
    run_pipeline,
)

HOST = "127.0.0.1"
PORT = 8765

WORKSPACE_DIR = Path(__file__).resolve().parents[2] / "workspace"
CHALLENGE_DATA_DIR = Path(__file__).resolve().parents[2] / "data_hackathon_baywa_re (1)"

# Whitelist of the workspace's own static files this server will serve, mapped to
# their content type -- deliberately not a general directory listing/traversal, just
# the handful of files the workspace actually has.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/assessment-data.js": ("assessment-data.js", "application/javascript; charset=utf-8"),
    "/evidence-tiers-data.js": ("evidence-tiers-data.js", "application/javascript; charset=utf-8"),
}

# Two of BayWa's own real challenge files (one target turbine with a gap, one
# reference turbine), so the Upload tab has something to try immediately rather
# than being a dead end for a visitor with no turbine CSVs on hand.
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SAMPLE_FILES = {
    "/sample/T2_data.xlsx": ("T2_data.xlsx", XLSX_CONTENT_TYPE),
    "/sample/O1_data.xlsx": ("O1_data.xlsx", XLSX_CONTENT_TYPE),
    "/sample/T2_power_curve.xlsx": ("T2_power_curve.xlsx", XLSX_CONTENT_TYPE),
}


def _parse_multipart(body: bytes, boundary: bytes) -> dict[str, list[dict]]:
    """Minimal multipart/form-data parser: returns {field_name: [{"filename":
    str|None, "data": bytes}, ...]} -- a LIST per field name, since the same field
    name (e.g. "wind_data") can appear more than once when a user selects several
    files for one <input type=file multiple> (BayWa ships one turbine per file, so
    a real upload is commonly several files under the same field name, not one).
    Deliberately simple -- splits on the boundary, then on the first blank line in
    each part to separate headers from the body."""

    parts: dict[str, list[dict]] = {}
    delimiter = b"--" + boundary
    for raw_part in body.split(delimiter):
        raw_part = raw_part.strip(b"\r\n")
        if not raw_part or raw_part == b"--":
            continue
        header_blob, _, content = raw_part.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", errors="replace")
        disposition_line = next(
            (line for line in headers.splitlines() if line.lower().startswith("content-disposition")),
            "",
        )
        name = None
        filename = None
        for piece in disposition_line.split(";"):
            piece = piece.strip()
            if piece.startswith("name="):
                name = piece[len("name="):].strip('"')
            elif piece.startswith("filename="):
                filename = piece[len("filename="):].strip('"')
        if name:
            parts.setdefault(name, []).append({"filename": filename, "data": content.rstrip(b"\r\n")})
    return parts


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # quieter default logging
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self) -> None:
        split = urlsplit(self.path)
        if split.path == "/insurance-report":
            self._handle_insurance_report(parse_qs(split.query))
            return

        # Strip a cache-busting query string (e.g. "/app.js?v=20261023c") -- the
        # workspace's own index.html references its static files that way.
        entry = STATIC_FILES.get(split.path)
        if entry is not None:
            filename, content_type = entry
            data = (WORKSPACE_DIR / filename).read_bytes()
            self._send_bytes(200, data, content_type)
            return

        sample_entry = SAMPLE_FILES.get(split.path)
        if sample_entry is not None:
            filename, content_type = sample_entry
            data = (CHALLENGE_DATA_DIR / filename).read_bytes()
            self._send_bytes(200, data, content_type, download_name=filename)
            return

        self.send_response(404)
        self.end_headers()

    def _send_bytes(self, status: int, data: bytes, content_type: str, download_name: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def _handle_insurance_report(self, query: dict[str, list[str]]) -> None:
        target = (query.get("target") or [""])[0].strip().upper()
        if not target:
            self._send_json_error(400, "Missing required ?target=<turbine id> (e.g. ?target=T3)")
            return
        try:
            result = generate_insurance_report(target)
        except Exception as exc:  # unknown target id, missing assessment file, etc.
            traceback.print_exc()
            self._send_json_error(400, f"{type(exc).__name__}: {exc}")
            return
        self._send_json(200, result)

    def do_POST(self) -> None:
        if self.path not in ("/run", "/preview"):
            self.send_response(404)
            self.end_headers()
            return

        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            self._send_json_error(400, "Expected multipart/form-data with a boundary")
            return
        boundary = content_type.split("boundary=")[-1].strip().encode("utf-8")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        parts = _parse_multipart(body, boundary)

        # Every uploaded data file -- wind-data and power-curve alike -- comes
        # in under one field name ("files"); classify_file_kind() sorts them by
        # their own column headers so the user never has to know in advance
        # which of two separate boxes each file belongs in. Shared between /run
        # and /preview (2026-10-24, Category 8) so the pre-run confirmation
        # summary classifies files the exact same way the real run will.
        uploaded_parts = [p for p in parts.get("files", []) if p["filename"]]
        if not uploaded_parts:
            self._send_json_error(400, "Missing required file upload -- select at least two files (a target turbine's data and a reference turbine's data)")
            return

        try:
            wind_data_items: list[tuple[bytes, str]] = []
            power_curve_items: list[tuple[bytes, str]] = []
            unknown_names: list[str] = []
            for p in uploaded_parts:
                kind = classify_file_kind(p["data"], p["filename"])
                if kind == "wind_data":
                    wind_data_items.append((p["data"], p["filename"]))
                elif kind == "power_curve":
                    power_curve_items.append((p["data"], p["filename"]))
                else:
                    unknown_names.append(p["filename"])
            if unknown_names:
                self._send_json_error(
                    400,
                    f"Could not recognize the column headers in: {', '.join(unknown_names)} -- "
                    "expected either wind-data columns (timestamp/turbine/wind speed) or "
                    "power-curve columns (wind speed/power).",
                )
                return
            if not wind_data_items:
                self._send_json_error(400, "No wind-data file recognized among the uploads -- need at least the target turbine's data plus one reference turbine's data")
                return

            if self.path == "/preview":
                # Lightweight per-file role guess for the upload form's pre-run
                # confirmation summary -- no reference selection, no model fit.
                self._send_json(200, {"files": describe_uploaded_files(wind_data_items, power_curve_items)})
                return

            wind_df = load_wind_data_files(wind_data_items)
            power_curve_df = None
            if power_curve_items:
                power_curve_df = load_power_curve(*power_curve_items[0])

            def _text_field(name: str) -> str | None:
                field_list = parts.get(name)
                if not field_list or not field_list[0]["data"]:
                    return None
                return field_list[0]["data"].decode("utf-8").strip() or None

            manual_start = _text_field("manual_start")
            manual_end = _text_field("manual_end")

            result = run_pipeline(wind_df, power_curve_df, manual_start, manual_end)
        except Exception as exc:  # local tool: surface the error to the caller, not a 500 page
            traceback.print_exc()
            self._send_json_error(400, f"{type(exc).__name__}: {exc}")
            return

        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"WindLens local tool running at http://{HOST}:{PORT}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

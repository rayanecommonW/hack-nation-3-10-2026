#!/usr/bin/env python3
"""Local preview server.

Runs the real WSGI application so the frontend talks to the same handler
production uses, rather than a static file server that 404s on /lab.

Uses waitress, not wsgiref. wsgiref serialises requests and mis-frames the
response body when the handler forks a subprocess, which showed up as the page
receiving headers and then an empty body. Waitress is threaded, production
grade, and behaves like the Vercel runtime does.

    ./scripts/devserver.py 8901
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from index import app  # noqa: E402


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    try:
        from waitress import serve
    except ImportError:
        raise SystemExit("waitress is required for the preview server: pip install waitress")
    print(f"PQS Lab on http://127.0.0.1:{port}  (WSGI, same handler as production)")
    serve(app, host="127.0.0.1", port=port, threads=8, ident="pqs-lab-dev")


if __name__ == "__main__":
    main()

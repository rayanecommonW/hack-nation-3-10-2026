#!/usr/bin/env python3
"""Local preview server.

Serves the real WSGI application so the frontend talks to the same handler
production uses, rather than a static file server that 404s on /lab.

    ./scripts/devserver.py 8899
"""
from __future__ import annotations

import os
import sys
from wsgiref.simple_server import make_server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from index import app  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"PQS Lab on http://127.0.0.1:{port}  (WSGI, same handler as production)")
    make_server("127.0.0.1", port, app).serve_forever()

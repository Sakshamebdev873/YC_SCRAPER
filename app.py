"""Launcher for the Cold Email Applier web UI.

    venv/Scripts/python.exe app.py

Initialises and seeds output/app.db, then serves the API and the built
frontend at http://127.0.0.1:8000 — localhost only, never exposed.
Run `cd frontend && npm run build` once so there is a dist/ to serve;
for frontend development use `npm run dev` on port 5173 instead.
"""

import argparse
import threading
import webbrowser

from dotenv import load_dotenv

load_dotenv()

from app.db import get_conn, init_db
from app.main import DIST, create_app
from app.seed import seed_all


def main():
    parser = argparse.ArgumentParser(description="Run the Cold Email Applier web UI")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    conn = get_conn()
    init_db(conn)
    result = seed_all(conn)
    conn.close()
    print(
        f"Seeded: {result['contacts']['inserted']} new contacts, "
        f"{result['templates']} templates, {result['sends']} send records."
    )

    if not DIST.exists():
        print("WARNING: frontend/dist not found — API only.")
        print("  Build it with: cd frontend && npm run build")

    url = f"http://127.0.0.1:{args.port}"
    print(f"Serving {url}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()

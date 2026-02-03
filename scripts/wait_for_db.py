import os
import sys
import time

import psycopg


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    wait_seconds = int(os.environ.get("DB_WAIT_SECONDS", "30"))
    deadline = time.time() + wait_seconds

    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with psycopg.connect(database_url, connect_timeout=3):
                print("DB is ready")
                return 0
        except Exception as exc:
            print(f"Waiting for DB (attempt {attempt})... ({exc})", file=sys.stderr)
            time.sleep(1)

    print(f"DB not ready after {wait_seconds}s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

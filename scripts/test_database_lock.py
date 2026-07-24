from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hold an exclusive SQLite lock for OMIP failure testing."
    )
    parser.add_argument("--database", default="backend/omip_v052.db")
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()

    database = Path(args.database).resolve()
    if not database.exists():
        raise SystemExit(f"Database not found: {database}")
    connection = sqlite3.connect(database, timeout=1.0)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        print(f"Exclusive lock held on {database} for {args.seconds:.1f} seconds.")
        time.sleep(max(0.1, args.seconds))
        connection.rollback()
    finally:
        connection.close()
    print("Database lock released.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

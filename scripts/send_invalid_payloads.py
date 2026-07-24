from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send deliberately invalid OMIP payloads."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    rejected = 0
    for index in range(max(1, args.count)):
        payload = {
            "schema_version": "0.3.1",
            "message_id": str(uuid4()),
            "vehicle_id": "INVALID-VEHICLE",
            "sensor_id": "INVALID-GNSS",
            "mission_id": "INVALID-MISSION",
            "sequence_no": index,
            "message_type": "GNSS",
            "payload": {"x_m": 1.0},
        }
        request = urllib.request.Request(
            f"{args.api_base.rstrip('/')}/api/v1/raw-messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=3).read()
        except urllib.error.HTTPError as exc:
            rejected += 1
            print(f"{index + 1}: rejected with HTTP {exc.code}")
        except OSError as exc:
            print(f"{index + 1}: connection failed: {exc}")
    print(f"Rejected {rejected}/{max(1, args.count)} invalid requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI boundary for bounded, offline classification in a separate process."""
import json
import os
import sys
import threading
import time

from .db import Store
from .organization import Organization


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if len(args) not in (2, 3, 4, 5):
        raise ValueError("database path and project required")
    parent = int(args[2]) if len(args) >= 3 else os.getppid()
    operation = args[3] if len(args) >= 4 else "suggest"
    if operation not in {"suggest", "graph"}:
        raise ValueError("unsupported worker operation")
    body = {"action": operation}
    if len(args) == 5:
        # Profile terms are user text: they arrive on stdin, never on the command line.
        if args[4] != "stdin" or operation != "suggest":
            raise ValueError("only suggest reads a request body from stdin")
        request = json.loads(sys.stdin.read(1_000_001)[:1_000_000] or "{}")
        if not isinstance(request, dict) or set(request) - {"profile", "scope_project"}:
            raise ValueError("worker request must be an object with an optional profile and scope_project")
        body.update(request)

    def guard():
        deadline = time.monotonic() + 120
        while os.getppid() == parent and time.monotonic() < deadline:
            time.sleep(0.2)
        os._exit(1)  # Abrupt parent death must not leave an orphan writing the DB.

    threading.Thread(target=guard, daemon=True).start()
    store = Store(args[0])
    try:
        store.init()
        print(json.dumps(Organization(store, project=args[1]).action(body),
                         ensure_ascii=False))
    finally:
        store.close()


if __name__ == "__main__":
    main()

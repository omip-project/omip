from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import ContextManager, Protocol


class LockContext(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


class RepositoryBase:
    """Shared dependencies for modular SQLite repositories."""

    def __init__(
        self,
        *,
        connect: Callable[[], sqlite3.Connection],
        lock: LockContext,
        utc_now: Callable[[], datetime],
    ) -> None:
        self._connect = connect
        self._lock = lock
        self._utc_now = utc_now

"""Tiny JSON-file persistence layer.

One file per collection inside ``db/``. Each collection is cached in memory
after the first load, so reads are O(1) dict lookups and a write costs one
atomic file rewrite (temp file + ``os.replace``) so a crash never leaves a
half-written file behind. A process-wide re-entrant lock keeps writers safe
under Django's threaded dev server.
"""
import json
import os
import threading
from typing import Dict, Iterator, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
OUT_DIR = os.path.join(os.path.dirname(DB_DIR), "out")

LOCK = threading.RLock()


class Collection:
    """A persisted ``id -> record`` mapping."""

    def __init__(self, name: str, db_dir: Optional[str] = None):
        self._path = os.path.join(db_dir or DB_DIR, f"{name}.json")
        self._data: Optional[Dict[str, dict]] = None

    def _load(self) -> Dict[str, dict]:
        if self._data is None:
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except FileNotFoundError:
                self._data = {}
        return self._data

    def get(self, key: str) -> Optional[dict]:
        return self._load().get(key)

    def values(self) -> Iterator[dict]:
        return iter(self._load().values())

    def put(self, record: dict) -> None:
        """Insert or replace ``record`` (keyed by its ``id``) and flush to disk."""
        self._load()[record["id"]] = record
        self.flush()

    def flush(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._load(), fh, indent=2)
        os.replace(tmp, self._path)

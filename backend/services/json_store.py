from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def ensure_json_file(path: str | Path, default_data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        atomic_write_json(target, default_data)


def read_json(path: str | Path, default_data: Any) -> Any:
    target = Path(path)
    ensure_json_file(target, default_data)
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = target.with_name(f"{target.name}.corrupt.{_stamp()}.bak")
        target.replace(backup)
        atomic_write_json(target, default_data)
        return default_data


def atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)


@contextmanager
def file_lock(path: str | Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    target = Path(path)
    lock_path = target.with_suffix(target.suffix + ".lock")
    target.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_seconds
    handle = None
    while time.time() < deadline:
        try:
            handle = lock_path.open("x", encoding="utf-8")
            handle.write(f"{time.time()}\n")
            handle.flush()
            break
        except FileExistsError:
            if time.time() - lock_path.stat().st_mtime > timeout_seconds:
                lock_path.unlink(missing_ok=True)
            time.sleep(0.05)
    if handle is None:
        raise TimeoutError(f"Could not acquire JSON lock: {lock_path}")
    try:
        yield
    finally:
        handle.close()
        lock_path.unlink(missing_ok=True)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

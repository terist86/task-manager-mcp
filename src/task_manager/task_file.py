"""Reader / writer for individual ``T-XXX.json`` task files.

JSON is the exclusive storage format. All data is stored as structured JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .schema import TaskData


class TaskFile:
    """Wraps a single ``T-XXX.json`` task file on disk."""

    def __init__(self, filepath: Path) -> None:
        self._path = Path(filepath)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.is_file()

    def read(self) -> TaskData:
        """Read and parse a ``T-XXX.json`` file into a :class:`TaskData` object."""
        if not self._path.is_file():
            return TaskData()
        raw = self._path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return TaskData()
        return TaskData.from_dict(data)

    def write(self, task: TaskData) -> None:
        """Serialize *task* to JSON and write to disk.

        Automatically calls :meth:`TaskData.touch` to refresh the timestamp.
        """
        task.touch()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self) -> bool:
        """Remove the task file from disk. Returns ``False`` if it did not exist."""
        if self._path.exists():
            self._path.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Static utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_next_id(tasks_dir: str | Path) -> str:
        """Scan *tasks_dir* for ``T-NNN.json`` files and return the next available ID."""
        tasks_dir = Path(tasks_dir)
        max_num = 0
        if tasks_dir.is_dir():
            for p in tasks_dir.glob("T-*.json"):
                try:
                    num = int(p.stem.split("-", 1)[-1])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        return f"T-{max_num + 1:03d}"



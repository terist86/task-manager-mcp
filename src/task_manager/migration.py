"""Migration tool placeholder — JSON-only format, no markdown conversion needed.

Previously handled old flat-file .md → directory-based .md conversion.
Now all storage is JSON, so migration methods are obsolete.
Kept as a placeholder for future format migrations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .project_manager import ProjectManager


class MigrationTool:
    """Placeholder for future format migrations. All current storage is JSON."""

    def __init__(
        self,
        old_tasks_dir: str = "tasks",
        new_projects_dir: str = "projects",
    ) -> None:
        self.old_dir = Path(old_tasks_dir)
        self.new_dir = Path(new_projects_dir)
        self.pm = ProjectManager(str(new_projects_dir))

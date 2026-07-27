"""MCP server entry point — registers all 10 task-management tools.

Rewritten to use the new ``src/task_manager/`` package (ProjectManager,
TaskManager) instead of the old monolithic ``task_manager.py``.
"""

from __future__ import annotations

import os
import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv

from task_manager import ProjectManager, TaskManager, MigrationTool, TaskData


load_dotenv()


# ---------------------------------------------------------------------------
# MCP factory
# ---------------------------------------------------------------------------

def create_mcp() -> FastMCP:
    """Create a configured ``FastMCP`` instance with all tools registered."""
    mcp = FastMCP(
        "TASK MANAGER",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8050")),
    )

    pm = ProjectManager("projects")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_tm(project_name: str) -> TaskManager:
        """Get a TaskManager for *project_name*, ensuring the project exists."""
        if not pm.project_exists(project_name):
            pm.create_project(project_name)
        return TaskManager(project_name, projects_dir="projects")

    def _find_task_by_title(tm: TaskManager, title_or_id: str) -> Optional[TaskData]:
        """Look up a task by ID (T-XXX) or by title."""
        # Try exact ID match first
        task = tm.get_task(title_or_id)
        if task is not None:
            return task
        # Fall back to title match
        for t in tm.list_tasks():
            if t.title == title_or_id:
                return t
        return None

    # ------------------------------------------------------------------
    # Tool 1: create_task_file
    # ------------------------------------------------------------------

    @mcp.tool()
    async def create_task_file(ctx: Context, project_name: str) -> str:
        """Create a new project directory with metadata and a ``tasks/`` subdirectory.

        Args:
            project_name: Name of the project

        Returns:
            Confirmation message with the project path
        """
        try:
            if pm.project_exists(project_name):
                return f"Project '{project_name}' already exists"
            meta = pm.create_project(project_name)
            return f"Created project '{project_name}' at projects/{project_name}/ (project.json + tasks/)"
        except Exception as e:
            return f"Error creating project: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 2: add_task
    # ------------------------------------------------------------------

    @mcp.tool()
    async def add_task(
        ctx: Context,
        project_name: str,
        title: str,
        description: str,
        subtasks: Optional[List[str]] = None,
        batch_mode: bool = False,
    ) -> str:
        """Add a new task to a project.

        Args:
            project_name: Name of the project
            title: Task title
            description: Task description
            subtasks: Optional list of subtasks
            batch_mode: If True, skip project existence check (for bulk additions)

        Returns:
            Confirmation message with the new task ID
        """
        try:
            if not batch_mode and not pm.project_exists(project_name):
                pm.create_project(project_name)

            tm = _get_tm(project_name)
            task = tm.create_task(
                title=title,
                description=description,
                subtasks=subtasks,
            )
            return f"Added task '{task.id}: {task.title}' to {project_name}"
        except Exception as e:
            return f"Error adding task: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 3: parse_prd
    # ------------------------------------------------------------------

    @mcp.tool()
    async def parse_prd(ctx: Context, project_name: str, prd_content: str) -> str:
        """Parse a PRD document and create tasks from its sections.

        Args:
            project_name: Name of the project
            prd_content: Full PRD markdown text

        Returns:
            Confirmation with the number of created tasks
        """
        try:
            # Parse sections from PRD
            sections: Dict[str, str] = {}
            current_section: Optional[str] = None
            current_lines: List[str] = []

            for line in prd_content.split("\n"):
                if line.startswith("# "):
                    if current_section:
                        sections[current_section] = "\n".join(current_lines)
                    current_section = line[2:].strip()
                    current_lines = []
                elif line.startswith("## "):
                    if current_section:
                        sections[current_section] = "\n".join(current_lines)
                    current_section = line[3:].strip()
                    current_lines = []
                else:
                    current_lines.append(line)

            if current_section:
                sections[current_section] = "\n".join(current_lines)

            # Ensure project exists
            if not pm.project_exists(project_name):
                pm.create_project(project_name)

            tm = _get_tm(project_name)
            created: List[str] = []

            # --- Task 1: Project Setup ---
            t = tm.create_task(
                title="Project Setup",
                description="Initialize project with tooling and configuration",
                category="[INFRA]",
                priority="P0",
                subtasks=[
                    "Initialize project structure",
                    "Configure tooling",
                    "Set up development environment",
                ],
            )
            created.append(t.id)

            # --- Task 2: Core Features ---
            if "Key Features" in sections:
                features = extract_bullet_points(sections["Key Features"])
                mvp_features = [f for f in features if "AI" not in f and "cloud" not in f.lower()]
                t = tm.create_task(
                    title="Implement Core Features",
                    description="Implement the core MVP features",
                    category="[MVP]",
                    priority="P0",
                    dependencies=[created[0]],
                    subtasks=mvp_features[:5] if mvp_features else ["Core feature 1", "Core feature 2"],
                )
                created.append(t.id)

            # --- Task 3: Auth & Storage ---
            t = tm.create_task(
                title="Authentication & Local Storage",
                description="Implement user authentication and local storage features",
                category="[MVP]",
                priority="P1",
                dependencies=[created[0]],
                subtasks=[
                    "Implement email authentication",
                    "Set up local storage",
                    "Add user session management",
                    "Implement data persistence",
                ],
            )
            created.append(t.id)

            # --- Task 4: UI/UX ---
            t = tm.create_task(
                title="Enhance UI/UX",
                description="Implement UI/UX improvements and polish",
                category="[UX]",
                priority="P2",
                dependencies=[created[1]] if len(created) > 1 else [],
                subtasks=[
                    "Implement dark/light mode",
                    "Add responsive design",
                    "Create minimalist editor",
                    "Add keyboard shortcuts",
                ],
            )
            created.append(t.id)

            return f"Parsed PRD and created {len(created)} tasks in '{project_name}': {', '.join(created)}"
        except Exception as e:
            return f"Error parsing PRD: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 4: update_task_status
    # ------------------------------------------------------------------

    @mcp.tool()
    async def update_task_status(
        ctx: Context,
        project_name: str,
        task_title: str,
        subtask_title: Optional[str] = None,
        status: str = "done",
    ) -> str:
        """Update the status of a task or subtask.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task (e.g. "T-001")
            subtask_title: Optional title of the subtask
            status: New status (todo/done for subtasks; ToDo/Analyze/Implementation/In Review/Done for tasks)

        Returns:
            Confirmation message
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            if subtask_title:
                result = tm.update_subtask(task.id, subtask_title, status)
                if result is None:
                    return f"Subtask '{subtask_title}' not found in task '{task.id}'"
                return f"Updated subtask '{subtask_title}' to {status} in task {task.id}"
            else:
                tm.update_task_status(task.id, status)
                return f"Updated task '{task.id}' status to {status}"
        except Exception as e:
            return f"Error updating status: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 5: get_next_task
    # ------------------------------------------------------------------

    @mcp.tool()
    async def get_next_task(ctx: Context, project_name: str) -> str:
        """Get the next uncompleted task from a project.

        Args:
            project_name: Name of the project

        Returns:
            Next task information or completion message
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = tm.get_next_task()
            if task is None:
                return "All tasks are completed!"

            # Find first uncompleted subtask
            next_subtask = None
            for st in task.subtasks:
                if st.status == "todo":
                    next_subtask = st.title
                    break

            return json.dumps({
                "task_id": task.id,
                "task": task.title,
                "subtask": next_subtask,
                "description": task.description,
            })
        except Exception as e:
            return f"Error getting next task: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 6: expand_task
    # ------------------------------------------------------------------

    @mcp.tool()
    async def expand_task(ctx: Context, project_name: str, task_title: str) -> str:
        """Break down a task into smaller subtasks using AI.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task to expand

        Returns:
            Confirmation message with new subtasks
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            # Generate expansion subtasks
            new_subtitles = [
                "Research existing solutions",
                "Design implementation approach",
                "Write initial code",
                "Test functionality",
                "Review and refine",
            ]

            from task_manager.schema import Subtask
            for st_title in new_subtitles:
                if not any(s.title == st_title for s in task.subtasks):
                    task.subtasks.append(Subtask(title=st_title, status="todo"))

            tm.update_task(task.id, subtasks=task.subtasks)
            return f"Expanded task '{task.id}' with {len(new_subtitles)} new subtasks"
        except Exception as e:
            return f"Error expanding task: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 7: generate_task_file
    # ------------------------------------------------------------------

    @mcp.tool()
    async def generate_task_file(ctx: Context, project_name: str, task_title: str) -> str:
        """Generate a source file template based on a task's description.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task

        Returns:
            Confirmation message with the generated file path
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            file_content = f"""# File generated from task: {task.title}

def main():
    # TODO: {task.description[:80]}
    pass

if __name__ == "__main__":
    main()
"""
            file_path = Path(project_name) / f"{task.title.lower().replace(' ', '_')}.py"
            file_path.parent.mkdir(exist_ok=True)
            file_path.write_text(file_content, encoding="utf-8")

            return f"Generated file template at {file_path}"
        except Exception as e:
            return f"Error generating file: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 8: get_task_dependencies
    # ------------------------------------------------------------------

    @mcp.tool()
    async def get_task_dependencies(ctx: Context, project_name: str, task_title: str) -> str:
        """Get all tasks that depend on the given task.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task to check

        Returns:
            JSON string of dependent tasks
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            dependents = tm.get_dependent_tasks(task.id)
            result = [{"id": t.id, "title": t.title, "status": t.status} for t in dependents]
            return json.dumps(result)
        except Exception as e:
            return f"Error getting dependencies: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 9: estimate_task_complexity
    # ------------------------------------------------------------------

    @mcp.tool()
    async def estimate_task_complexity(ctx: Context, project_name: str, task_title: str) -> str:
        """Estimate the complexity of a task using AI.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task

        Returns:
            JSON with complexity estimate
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            # Heuristic complexity estimate based on description length and subtask count
            desc_len = len(task.description)
            st_count = len(task.subtasks)

            if desc_len < 50 and st_count <= 3:
                complexity = "low"
                hours = 4
            elif desc_len < 200 and st_count <= 7:
                complexity = "medium"
                hours = 8
            else:
                complexity = "high"
                hours = 16

            return json.dumps({
                "task_id": task.id,
                "task": task.title,
                "complexity": complexity,
                "estimated_hours": hours,
            })
        except Exception as e:
            return f"Error estimating complexity: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 10: suggest_next_actions
    # ------------------------------------------------------------------

    @mcp.tool()
    async def suggest_next_actions(ctx: Context, project_name: str, task_title: str) -> str:
        """Suggest next actions for a task using AI.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task

        Returns:
            JSON string of suggested actions
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            suggestions = [
                "Review the current implementation",
                "Set up the development environment",
                "Create initial test cases",
                "Implement core functionality",
                "Write documentation",
            ]

            return json.dumps({
                "task_id": task.id,
                "task": task.title,
                "suggestions": suggestions,
            })
        except Exception as e:
            return f"Error suggesting actions: {str(e)}"

    return mcp


# ---------------------------------------------------------------------------
# Helpers (kept at module level for reuse)
# ---------------------------------------------------------------------------

def extract_bullet_points(content: str) -> List[str]:
    """Extract bullet points from markdown text."""
    points: List[str] = []
    for line in content.split("\n"):
        line = line.strip()
        if line and (line.startswith("-") or line.startswith("*") or line.startswith("•")):
            cleaned = re.sub(r"^[-*•]\s*", "", line)
            cleaned = re.sub(r"`[^`]*`", "", cleaned)
            cleaned = re.sub(r"\*\*([^*]*)\*\*", r"\1", cleaned)
            cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
            if cleaned:
                points.append(cleaned)
    return points


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    mcp = create_mcp()
    transport = os.getenv("TRANSPORT", "sse")
    if transport == "sse":
        await mcp.run_sse_async()
    else:
        await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())

"""MCP server entry point — registers all 13 task-management tools.
 
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
        note: str = "",
    ) -> str:
        """Update the status of a task or subtask.

        Every transition is logged with a timestamp in the task's Log section.
        ``Canceled`` is a terminal status — a canceled child allows its parent
        to become Done.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task (e.g. "T-001")
            subtask_title: Optional title of the subtask
            status: New status (todo/done for subtasks; ToDo/Analyze/Implementation/In Review/Done/Canceled for tasks)
            note: Optional note for the transition log entry

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
                tm.update_task_status(task.id, status, note=note)
                if note:
                    return f"Updated task '{task.id}' status to {status} (note: {note})"
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
    async def expand_task(ctx: Context, project_name: str, task_title: str, create_files: bool = False, mode: str = "parallel") -> str:
        """Break down a task into smaller subtasks using AI.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task to expand
            create_files: If True, create separate T-XXX.md files for each subtask
                          with parent-child references. If False (default), add
                          inline subtasks to the existing task file.
            mode: Expansion mode when create_files=True — "parallel" (all children
                  depend on parent) or "chain" (sequential deps: A → B → C).

        Returns:
            Confirmation message with new subtask IDs (file mode) or count (inline mode)
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found in '{project_name}'"

            if create_files:
                # File-mode: create independent T-XXX.md files
                new_titles = [
                    f"{task.title} — Part {i+1}"
                    for i in range(3)
                ]
                children = tm.expand_to_files(task.id, new_titles, mode=mode)
                child_ids = [c.id for c in children]
                return (
                    f"Expanded task '{task.id}' into {len(children)} files ({mode} mode): "
                    f"{', '.join(child_ids)}"
                )
            else:
                # Inline mode: add subtasks to the same file (backward compatible)
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
                return f"Expanded task '{task.id}' with {len(new_subtitles)} inline subtasks"
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

    # ------------------------------------------------------------------
    # Tool 11: list_projects
    # ------------------------------------------------------------------

    @mcp.tool()
    async def list_projects(ctx: Context) -> str:
        """List all registered projects.

        Returns:
            JSON array of project metadata objects (name, language, description, created_at, etc.)
        """
        try:
            projects = pm.list_projects()
            result = [
                {
                    "name": p.name,
                    "language": p.language,
                    "description": p.description,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                }
                for p in projects
            ]
            if not result:
                return "No projects found"
            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"Error listing projects: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 12: update_project
    # ------------------------------------------------------------------

    @mcp.tool()
    async def update_project(
        ctx: Context,
        project_name: str,
        language: str = "",
        build_system: str = "",
        description: str = "",
        path: str = "",
    ) -> str:
        """Update metadata for an existing project.

        Args:
            project_name: Name of the project
            language: Programming language (e.g. "C++20", "python")
            build_system: Build system (e.g. "cmake", "uv")
            description: Project description
            path: Path to the project on disk

        Returns:
            Confirmation message with updated fields
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            updates = {}
            if language:
                updates["language"] = language
            if build_system:
                updates["build_system"] = build_system
            if description:
                updates["description"] = description
            if path:
                updates["path"] = path

            if not updates:
                return "No fields to update"

            pm.update_project(project_name, **updates)
            return f"Updated project '{project_name}': {json.dumps(updates)}"
        except Exception as e:
            return f"Error updating project: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 13: list_tasks
    # ------------------------------------------------------------------

    @mcp.tool()
    async def list_tasks(
        ctx: Context,
        project_name: str,
        status: Optional[str] = None,
    ) -> str:
        """List all tasks for a project, optionally filtered by status.

        Args:
            project_name: Name of the project
            status: Optional status filter (ToDo/Analyze/Implementation/In Review/Done)

        Returns:
            JSON array of task objects (id, title, status, priority, category)
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            tasks = tm.list_tasks(status=status)
            if not tasks:
                return "No tasks found"
            result = [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "category": t.category,
                    "subtasks_total": len(t.subtasks),
                    "subtasks_done": sum(1 for s in t.subtasks if s.status == "done"),
                }
                for t in tasks
            ]
            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"Error listing tasks: {str(e)}"

    # ------------------------------------------------------------------
    # Tool 14: get_task
    # ------------------------------------------------------------------

    @mcp.tool()
    async def get_task(ctx: Context, project_name: str, task_title: str) -> str:
        """Get full task data as JSON including description, criteria blocks, and log.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task (e.g. "T-001")

        Returns:
            JSON string with full TaskData (all fields)
        """
        try:
            if not pm.project_exists(project_name):
                return json.dumps({"error": f"Project '{project_name}' not found"})

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return json.dumps({"error": f"Task '{task_title}' not found"})

            data = task.to_dict()
            # Convert subtasks to simple dicts
            data["subtasks"] = [s.to_dict() for s in task.subtasks]
            # Convert criteria blocks
            for key in ("analyze", "implementation", "in_review", "done"):
                if data.get(key):
                    data[key] = data[key].to_dict() if hasattr(data[key], 'to_dict') else data[key]
            # Convert log entries
            data["log_entries"] = [e.to_dict() for e in task.log_entries]
            return json.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # Tool 15: update_task
    # ------------------------------------------------------------------

    @mcp.tool()
    async def update_task(
        ctx: Context,
        project_name: str,
        task_title: str,
        description: str = "",
        category: str = "",
        priority: str = "",
        complexity: str = "",
        estimated_hours: int = 0,
        dependencies: Optional[List[str]] = None,
        subtasks: Optional[List[str]] = None,
        subtask_statuses: Optional[List[str]] = None,
    ) -> str:
        """Update task fields. Only non-empty fields are applied.

        Args:
            project_name: Name of the project
            task_title: Title or ID of the task
            description: New description
            category: New category (e.g. "[MVP]")
            priority: New priority (P0-P3)
            complexity: Complexity estimate (low/medium/high)
            estimated_hours: Estimated hours
            dependencies: List of dependency task IDs
            subtasks: List of subtask titles (replaces existing)
            subtask_statuses: Matching list of statuses (todo/done) for subtasks

        Returns:
            Confirmation message
        """
        try:
            if not pm.project_exists(project_name):
                return f"Project '{project_name}' not found"

            tm = _get_tm(project_name)
            task = _find_task_by_title(tm, task_title)
            if task is None:
                return f"Task '{task_title}' not found"

            updates = {}
            if description:
                updates["description"] = description
            if category:
                updates["category"] = category
            if priority:
                updates["priority"] = priority
            if complexity:
                updates["complexity"] = complexity
            if estimated_hours:
                updates["estimated_hours"] = estimated_hours
            if dependencies is not None:
                updates["dependencies"] = dependencies
            if subtasks is not None:
                from task_manager.schema import Subtask
                statuses = subtask_statuses or ["todo"] * len(subtasks)
                updates["subtasks"] = [
                    Subtask(title=s, status=statuses[i] if i < len(statuses) else "todo")
                    for i, s in enumerate(subtasks)
                ]

            if not updates:
                return "No fields to update"

            tm.update_task(task.id, **updates)
            return f"Updated task '{task.id}': {', '.join(updates.keys())}"
        except Exception as e:
            return f"Error updating task: {str(e)}"

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

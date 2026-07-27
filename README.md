# Task Manager MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for multi-project task management with directory-based storage. Provides a comprehensive task management system with support for project organization, task tracking, PRD parsing, and AI-assisted task expansion.

## Overview

This MCP server enables AI agents to manage tasks, track project progress, and break down tasks into independent subtask files. Each project is stored as a directory under `projects/` with its own metadata (`project.json`) and individual task files (`tasks/T-XXX.md`) following the standard Task File Template.

## Features

### Project Management

| Tool | Description |
|------|-------------|
| `create_task_file` | Create a new project directory with metadata and a `tasks/` subdirectory |
| `list_projects` | List all registered projects with metadata |
| `update_project` | Update project metadata (language, build system, description, path) |

### Task Management

| Tool | Description |
|------|-------------|
| `add_task` | Add a new task to a project (auto-assigned T-XXX ID) |
| `list_tasks` | List all tasks for a project, optionally filtered by status |
| `update_task_status` | Update the status of a task or subtask |
| `get_next_task` | Get the next uncompleted task from a project |
| `get_task_dependencies` | Get all tasks that depend on a given task |

### AI-Assisted Planning

| Tool | Description |
|------|-------------|
| `parse_prd` | Parse a PRD document and create structured tasks |
| `expand_task` | Break down a task into subtasks — inline mode or file mode with parent-child references |
| `estimate_task_complexity` | Estimate task complexity (low/medium/high) and time requirements |
| `suggest_next_actions` | Get AI-powered suggestions for next actions on a task |
| `generate_task_file` | Generate a source file template based on a task description |

## Data Structure

```
projects/
  <project-name>/
    project.json              # Project metadata
    tasks/
      T-001.md                # Individual task file
      T-002.md
      ...
```

### Project Metadata (`project.json`)

```json
{
  "name": "my-project",
  "path": "/home/user/my-project",
  "language": "python",
  "build_system": "uv",
  "description": "Description of the project",
  "created_at": "2026-07-27T10:00:00Z",
  "updated_at": "2026-07-27T10:00:00Z"
}
```

### Task File Format (`T-XXX.md`)

Each task follows the standard Task File Template:

```markdown
# T-001: Task Title

## Metadata
- **ID:** T-001
- **Priority:** P0
- **Dependencies:** T-002
- **Parent Task:** T-000
- **Child Tasks:** T-003, T-004
- **Complexity:** medium
- **Estimate:** 8 hours

## Status: ToDo

## Log
### 2026-07-27 — Analyze → Implementation
- Transition validation: ✅ PASS
- Note: Ready to code

## Description
Task description text.

## Analyze
### Input Criteria
- [ ] ...
### Output Criteria (-> Implementation)
- [ ] ...

## Implementation
...

## In Review
...

## Done
- [ ] Task completed

### Subtasks
- [ ] Subtask 1
- [x] Subtask 2
```

## Prerequisites

- Python 3.12+
- Docker (optional, for containerized deployment)

## Installation

### Using uv

```bash
pip install uv
git clone <repository-url>
cd task-manager-mcp
uv pip install -e .
cp .env.example .env
```

### Using Docker

```bash
docker build -t task-manager-mcp --build-arg PORT=8050 .
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TRANSPORT` | Transport protocol (`sse` or `stdio`) | `sse` |
| `HOST` | Host for SSE transport | `0.0.0.0` |
| `PORT` | Port for SSE transport | `8050` |

## Running the Server

```bash
# Using Python
source .venv/bin/activate && python src/main.py

# Using Docker
docker compose up -d
```

## MCP Client Configuration

### SSE

```json
{
  "mcpServers": {
    "task-manager": {
      "transport": "sse",
      "url": "http://localhost:8050/sse"
    }
  }
}
```

### Stdio

```json
{
  "mcpServers": {
    "task-manager": {
      "command": "python3",
      "args": ["src/main.py"],
      "env": { "TRANSPORT": "stdio" }
    }
  }
}
```

## Tool Reference

All tools return string messages suitable for display to the user.

### `create_task_file`

Create a new project directory with metadata and a `tasks/` subdirectory.

```
create_task_file(project_name: str) -> str
```

### `add_task`

Add a new task to a project. Auto-assigns the next T-XXX ID.

```
add_task(
    project_name: str,
    title: str,
    description: str,
    subtasks: Optional[List[str]] = None,
    batch_mode: bool = False,
) -> str
```

### `parse_prd`

Parse a PRD document and create structured tasks from its sections.

```
parse_prd(project_name: str, prd_content: str) -> str
```

### `update_task_status`

Update the status of a task or subtask. Every transition is logged in the task's `## Log` section with timestamp, validation result, and optional note.

**Task statuses:** `ToDo`, `Analyze`, `Implementation`, `In Review`, `Done`, `Canceled`
**Subtask statuses:** `todo`, `done`

**Transition flow:**
```
ToDo → Analyze → Implementation → In Review → Done
            ▲                         │
            └─────────────────────────┘
                In Review → Analyze (rejected)
Any → Canceled (terminal, dead end)
```

When a task reaches `Done` or `Canceled` and it has a parent, status propagation checks siblings and auto-promotes the parent.

```
update_task_status(
    project_name: str,
    task_title: str,
    subtask_title: Optional[str] = None,
    status: str = "done",
    note: str = "",
) -> str
```

### `get_next_task`

Get the next uncompleted task from a project (sorted by status priority).

```
get_next_task(project_name: str) -> str
```

### `expand_task`

Break down a task into smaller subtasks. Supports two modes:

- **Inline mode** (`create_files=False`, default) — adds subtasks as checkboxes inside the same T-XXX.md file (backward compatible).
- **File mode** (`create_files=True`) — creates independent T-XXX.md files for each subtask with parent-child references and configurable dependency chains.

```
expand_task(
    project_name: str,
    task_title: str,
    create_files: bool = False,
    mode: str = "parallel",
) -> str
```

**Modes (file mode only):**
- `"parallel"` — all children depend on the parent task only
- `"chain"` — sequential dependencies (T-003 → T-004 → T-005)

### `generate_task_file`

Generate a source file template based on a task's description.

```
generate_task_file(project_name: str, task_title: str) -> str
```

### `get_task_dependencies`

Get all tasks that list the given task in their dependencies.

```
get_task_dependencies(project_name: str, task_title: str) -> str
```

### `estimate_task_complexity`

Estimate task complexity using heuristic analysis of description length and subtask count.

```
estimate_task_complexity(project_name: str, task_title: str) -> str
```

Returns JSON: `{"task_id": "T-001", "task": "...", "complexity": "medium", "estimated_hours": 8}`

### `suggest_next_actions`

Get AI-powered suggestions for the next steps on a task.

```
suggest_next_actions(project_name: str, task_title: str) -> str
```

### `list_projects`

List all registered projects with their metadata.

```
list_projects() -> str
```

### `update_project`

Update metadata fields for an existing project. Only non-empty fields are applied.

```
update_project(
    project_name: str,
    language: str = "",
    build_system: str = "",
    description: str = "",
    path: str = "",
) -> str
```

### `list_tasks`

List all tasks for a project, optionally filtered by status.

```
list_tasks(project_name: str, status: Optional[str] = None) -> str
```

## Task Expansion — Parent-Child References

When `expand_task` is called with `create_files=True`, child tasks are created with:

- **`parent_task_id`** — references the parent task
- **`dependencies`** — depends on the parent (parallel) or previous sibling (chain)
- Parent's **`child_task_ids`** — tracks all children (extended on re-expansion)
- **Log transition history** — every status change is recorded with timestamp and optional note
- **Canceled status** — terminal status; canceled children unblock parent completion
- **Status propagation** — Done/Canceled children auto-promote parent
- **Transition validation** — enforces valid state flow (ToDo→Analyze→Implementation→In Review→Done/Analyze)

Example after expanding T-001 with `create_files=True, mode="parallel"`:

```
T-001 (Parent)     Child Tasks: T-002, T-003
  T-002 (Child)    Parent Task: T-001, Dependencies: T-001
  T-003 (Child)    Parent Task: T-001, Dependencies: T-001
```

## Building Your Own Server

This project provides a modular foundation for building task management MCP servers. To extend it:

1. Add new data models in `src/task_manager/schema.py`
2. Add file I/O logic in `src/task_manager/task_file.py`
3. Implement CRUD operations in `src/task_manager/task_manager.py`
4. Register new MCP tools in `src/main.py` using `@mcp.tool()`

### Package Structure

```
src/
  main.py                     # Entry point + MCP tool registration (13 tools)
  task_manager/
    __init__.py               # Public API exports
    schema.py                 # Data models (ProjectMetadata, TaskData, Subtask, CriteriaBlock, LogEntry)
    task_file.py              # Individual T-XXX.md file reader/writer/parser
    project_manager.py        # Project-level CRUD + project.json metadata
    task_manager.py           # Per-project task CRUD + expand_to_files + status propagation
    migration.py              # Old flat-file → new directory-based migration
```

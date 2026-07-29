# Task Manager MCP — Tools Reference

## Architecture

The server stores data in a directory-based structure under `projects/`:

```
projects/
  <project-name>/
    project.json              # Metadata: name, path, language, build_system, description
    tasks/
      T-001.md                # Individual task file (Task File Template format)
      T-002.md
```

Source code is modularized under `src/task_manager/`:

| Module | Responsibility |
|--------|---------------|
| `schema.py` | `ProjectMetadata`, `TaskData`, `Subtask`, `CriteriaBlock` dataclasses |
| `task_file.py` | `TaskFile` — read/write/parse individual T-XXX.md files |
| `project_manager.py` | `ProjectManager` — project CRUD + project.json |
| `task_manager.py` | `TaskManager` — per-project task CRUD + `expand_to_files` + status propagation |
| `migration.py` | `MigrationTool` — convert old tasks/*.md to projects/ structure |

---

## All 15 MCP Tools

### 1. `create_task_file`
Creates a project directory with `project.json` and `tasks/` subdirectory.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |

### 2. `add_task`
Adds a new task with an auto-assigned `T-XXX` ID.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `title` | `str` | yes |
| `description` | `str` | yes |
| `subtasks` | `List[str]` | no |
| `batch_mode` | `bool` | no |

### 3. `parse_prd`
Parses a PRD markdown document and creates structured tasks.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `prd_content` | `str` | yes |

### 4. `update_task_status`
Updates task or subtask status. **Task statuses:** `ToDo`, `Analyze`, `Implementation`, `In Review`, `Done`. **Subtask statuses:** `todo`, `done`. Automatically triggers status propagation when child reaches Done.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes (title or ID, e.g. "T-001") |
| `subtask_title` | `str` | no |
| `status` | `str` | default: `"done"` |

### 5. `get_next_task`
Returns the first non-Done task, sorted by status priority.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |

### 6. `expand_task` ⭐
Breaks a task into subtasks. **Two modes:**

- **File** (`create_files=True`, default) — creates independent T-XXX.md files with parent-child references
- **Inline** (`create_files=False`) — adds checkboxes to the same file (backward compatible)

| Param | Type | Required | Default |
|-------|------|----------|---------|
| `project_name` | `str` | yes | |
| `task_title` | `str` | yes | |
| `create_files` | `bool` | no | `True` |
| `mode` | `str` | no | `"parallel"` |

**Modes:** `"parallel"` (all children → parent), `"chain"` (sequential deps)

### 7. `generate_task_file`
Generates a source file template from a task description.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes |

### 8. `get_task_dependencies`
Returns all tasks that list the given task in their `Dependencies`.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes |

### 9. `estimate_task_complexity`
Heuristic complexity estimate (low/medium/high) based on description length and subtask count.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes |

### 10. `suggest_next_actions`
Returns a list of suggested next actions for a task.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes |

### 11. `list_projects`
Lists all registered projects with their metadata (name, language, description, timestamps).

No parameters.

### 12. `update_project`
Updates project metadata. Only non-empty fields are applied.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `language` | `str` | no |
| `build_system` | `str` | no |
| `description` | `str` | no |
| `path` | `str` | no |

### 13. `list_tasks`
Lists all tasks for a project, optionally filtered by status.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `status` | `str` | no (ToDo/Analyze/Implementation/In Review/Done/Canceled) |

### 14. `get_task`
Returns full task data as JSON including description, criteria blocks, log entries, and all metadata.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes |

### 15. `update_task`
Patches task fields. Only non-empty fields are applied.

| Param | Type | Required |
|-------|------|----------|
| `project_name` | `str` | yes |
| `task_title` | `str` | yes |
| `description` | `str` | no |
| `category` | `str` | no |
| `priority` | `str` | no (P0-P3) |
| `complexity` | `str` | no (low/medium/high) |
| `estimated_hours` | `int` | no |
| `dependencies` | `List[str]` | no |
| `subtasks` | `List[str]` | no (replaces existing) |
| `subtask_statuses` | `List[str]` | no (todo/done, matches subtasks) |

---

## Task File Format

Tasks are stored as JSON files (`T-XXX.json`):

```json
{
  "id": "T-001",
  "title": "Task Title",
  "status": "ToDo",
  "priority": "P0",
  "dependencies": ["T-002"],
  "parent_task_id": "T-000",
  "child_task_ids": ["T-003", "T-004"]
}
```

For the full schema, see the [README](README.md).

---

When using `expand_task(create_files=True)`:

- Each child gets `parent_task_id` and a `Dependencies` entry
- Parent's `child_task_ids` is **extended** on re-expansion (preserves existing children)
- Marking a child `Done` triggers `_propagate_to_parent()` — if all siblings are Done, parent auto-promotes
- Propagation is recursive up the entire hierarchy

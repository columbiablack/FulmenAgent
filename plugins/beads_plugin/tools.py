import logging
import subprocess
import json
import shutil
import os
from typing import Dict, Any

from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


def _run_bd(args: list, cwd: str = None) -> Dict[str, Any]:
    """Run a bd CLI command and return parsed output."""
    bd_path = shutil.which("bd")
    if not bd_path:
        return {"status": "error", "output": "bd CLI not found. Install with: npm install -g @beads/bd"}

    cmd = [bd_path] + args + ["--json", "--quiet"]
    work_dir = cwd or os.environ.get("BEADS_WORKDIR", os.getcwd())

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=work_dir
        )

        output = result.stdout.strip()
        stderr = result.stderr.strip()

        # Try to parse JSON output
        if output:
            try:
                parsed = json.loads(output)
                return {"status": "success", "output": output, "data": parsed}
            except json.JSONDecodeError:
                return {"status": "success", "output": output}

        if result.returncode != 0:
            # bd may output errors to stderr
            error_msg = stderr or f"bd exited with code {result.returncode}"
            # Filter out warning lines, keep actual errors
            error_lines = [l for l in error_msg.split("\n") if not l.startswith("⚠") and not l.startswith("warning:")]
            clean_error = "\n".join(error_lines).strip() or error_msg
            return {"status": "error", "output": clean_error}

        return {"status": "success", "output": stderr or "(no output)"}

    except subprocess.TimeoutExpired:
        return {"status": "error", "output": "bd command timed out after 30 seconds."}
    except Exception as e:
        logger.error(f"[BeadsTask] Error running bd: {e}", exc_info=True)
        return {"status": "error", "output": f"Failed to run bd: {e}"}


class BeadsTaskTool(BaseTool):
    """Persistent task memory using Beads (bd) CLI."""

    def __init__(self):
        super().__init__(
            name="beads_task",
            description=(
                "Persistent task memory using Beads. Tasks survive hub restarts. "
                "Actions: 'init' (initialize beads), 'create' (new task), 'list' (list tasks), "
                "'ready' (unblocked tasks), 'show' (task details), 'update' (modify task), "
                "'close' (close task), 'dep_add' (add dependency), 'search' (find tasks). "
                "Requires 'action' dict with 'type' and relevant parameters. "
                "Example: {\"action\": {\"type\": \"create\", \"title\": \"Check weather\", \"priority\": 1}}"
            )
        )

    def run(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", {})
        action_type = action.get("type") or kwargs.get("action_type")

        if not action_type:
            return {
                "status": "error",
                "output": "action.type is required. Available: init, create, list, ready, show, update, close, dep_add, search"
            }

        if action_type == "init":
            return self._init(action)
        elif action_type == "create":
            return self._create(action)
        elif action_type == "list":
            return self._list(action)
        elif action_type == "ready":
            return self._ready(action)
        elif action_type == "show":
            return self._show(action)
        elif action_type == "update":
            return self._update(action)
        elif action_type == "close":
            return self._close(action)
        elif action_type == "dep_add":
            return self._dep_add(action)
        elif action_type == "search":
            return self._search(action)
        else:
            return {
                "status": "error",
                "output": f"Unknown action: {action_type}. Available: init, create, list, ready, show, update, close, dep_add, search"
            }

    def _init(self, action: dict) -> Dict[str, Any]:
        """Initialize Beads in a directory."""
        args = ["init"]
        if action.get("stealth"):
            args.append("--stealth")
        return _run_bd(args, cwd=action.get("path"))

    def _create(self, action: dict) -> Dict[str, Any]:
        """Create a new task."""
        title = action.get("title")
        if not title:
            return {"status": "error", "output": "title is required for create."}

        args = ["create", title]

        priority = action.get("priority")
        if priority is not None:
            args.extend(["-p", str(priority)])

        task_type = action.get("task_type")
        if task_type:
            args.extend(["--type", task_type])

        assignee = action.get("assignee")
        if assignee:
            args.extend(["--assignee", assignee])

        body = action.get("body") or action.get("description")
        if body:
            args.extend(["--body", body])

        result = _run_bd(args)
        if result["status"] == "success" and "data" in result:
            task_id = result["data"].get("id", "")
            result["output"] = f"Task created: {task_id} - {title}"
        return result

    def _list(self, action: dict) -> Dict[str, Any]:
        """List tasks with optional filters."""
        args = ["list"]

        status = action.get("status")
        if status:
            args.extend(["--status", status])

        assignee = action.get("assignee")
        if assignee:
            args.extend(["--assignee", assignee])

        priority = action.get("priority")
        if priority is not None:
            args.extend(["-p", str(priority)])

        limit = action.get("limit")
        if limit:
            args.extend(["--limit", str(limit)])

        result = _run_bd(args)
        if result["status"] == "success" and "data" in result:
            data = result["data"]
            if isinstance(data, list):
                result["output"] = f"Found {len(data)} task(s)."
                # Summarize for the LLM
                summaries = []
                for t in data[:10]:
                    summaries.append(f"  {t.get('id')}: [{t.get('status')}] P{t.get('priority', '?')} - {t.get('title', '?')}")
                if summaries:
                    result["output"] += "\n" + "\n".join(summaries)
        return result

    def _ready(self, action: dict) -> Dict[str, Any]:
        """List tasks with no open blockers."""
        result = _run_bd(["ready"])
        if result["status"] == "success" and "data" in result:
            data = result["data"]
            if isinstance(data, list):
                result["output"] = f"{len(data)} ready task(s)."
                summaries = []
                for t in data[:10]:
                    summaries.append(f"  {t.get('id')}: P{t.get('priority', '?')} - {t.get('title', '?')}")
                if summaries:
                    result["output"] += "\n" + "\n".join(summaries)
                else:
                    result["output"] = "No ready tasks. All tasks are either blocked or closed."
        return result

    def _show(self, action: dict) -> Dict[str, Any]:
        """Show details of a specific task."""
        task_id = action.get("task_id")
        if not task_id:
            return {"status": "error", "output": "task_id is required for show."}
        return _run_bd(["show", task_id])

    def _update(self, action: dict) -> Dict[str, Any]:
        """Update a task."""
        task_id = action.get("task_id")
        if not task_id:
            return {"status": "error", "output": "task_id is required for update."}

        args = ["update", task_id]

        if action.get("claim"):
            args.append("--claim")

        status = action.get("status")
        if status:
            args.extend(["--status", status])

        priority = action.get("priority")
        if priority is not None:
            args.extend(["-p", str(priority)])

        title = action.get("title")
        if title:
            args.extend(["--title", title])

        assignee = action.get("assignee")
        if assignee:
            args.extend(["--assignee", assignee])

        description = action.get("description") or action.get("comment") or action.get("notes")
        if description:
            args.extend(["--description", description])

        return _run_bd(args)

    def _close(self, action: dict) -> Dict[str, Any]:
        """Close a task."""
        task_id = action.get("task_id")
        if not task_id:
            return {"status": "error", "output": "task_id is required for close."}

        args = ["close", task_id]

        reason = action.get("reason") or action.get("comment")
        if reason:
            args.extend(["--reason", reason])

        result = _run_bd(args)
        if result["status"] == "success":
            result["output"] = f"Task {task_id} closed."
        return result

    def _dep_add(self, action: dict) -> Dict[str, Any]:
        """Add a dependency between tasks."""
        child_id = action.get("child_id")
        parent_id = action.get("parent_id")
        if not child_id or not parent_id:
            return {"status": "error", "output": "child_id and parent_id are required for dep_add."}

        args = ["dep", "add", child_id, parent_id]

        dep_type = action.get("dep_type")
        if dep_type:
            args.extend(["--type", dep_type])

        result = _run_bd(args)
        if result["status"] == "success":
            result["output"] = f"Dependency added: {child_id} blocked by {parent_id}."
        return result

    def _search(self, action: dict) -> Dict[str, Any]:
        """Search tasks by text."""
        query = action.get("query")
        if not query:
            return {"status": "error", "output": "query is required for search."}

        result = _run_bd(["search", query])
        if result["status"] == "success" and "data" in result:
            data = result["data"]
            if isinstance(data, list):
                result["output"] = f"Found {len(data)} result(s) for '{query}'."
                summaries = []
                for t in data[:10]:
                    summaries.append(f"  {t.get('id')}: [{t.get('status')}] - {t.get('title', '?')}")
                if summaries:
                    result["output"] += "\n" + "\n".join(summaries)
        return result


def get_tools():
    """Entry point for plugin discovery."""
    logger.info("Initializing Beads Task Memory plugin.")
    try:
        # Check if bd CLI is available
        bd_path = shutil.which("bd")
        if not bd_path:
            logger.warning("bd CLI not found. Install with: npm install -g @beads/bd")
            logger.warning("Beads plugin will load but commands will fail until bd is installed.")

        tool = BeadsTaskTool()
        logger.info(f"BeadsTaskTool created: {tool.name}")
        return [tool]
    except Exception as e:
        logger.error(f"Error creating BeadsTaskTool: {e}", exc_info=True)
        return []

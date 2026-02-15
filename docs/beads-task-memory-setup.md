# Beads Task Memory Plugin — Setup Guide

Beads gives your agents persistent task memory that survives hub restarts. Agents can create tasks, track dependencies, coordinate with each other, and pick up work where they left off.

Built on [steveyegge/beads](https://github.com/steveyegge/beads) — a task tracker designed specifically for AI agents.

---

## Why Beads?

Without Beads, agent tasks live in `hub_memory` — when the hub restarts, everything is gone. Agents can't:
- Remember what they were working on
- Coordinate tasks with other agents
- Track which tasks depend on others
- Pick up unfinished work

Beads fixes all of this with a persistent task database.

---

## Setup

### 1. Install the bd CLI

```bash
npm install -g @beads/bd
```

Verify it works:
```bash
bd --version
```

### 2. Initialize Beads in Your Project

```bash
cd /root/agent
bd init
```

This creates a `.beads/` directory with a `issues.jsonl` file for persistent storage.

### 3. Restart the Hub

The Beads Task Memory plugin loads automatically. Restart the hub and verify it appears in the dashboard under the Plugins tab.

That's it — no API keys, no config needed.

---

## How Agents Use It

The plugin provides a single tool: **`beads_task`** with 9 actions.

### Create a Task

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "create",
      "title": "Check weather for Tacoma WA",
      "priority": 0,
      "task_type": "task"
    }
  }
}
```

**Priority levels:** 0 = critical, 1 = high, 2 = medium, 3 = low, 4 = lowest

**Task types:** `task`, `bug`, `feature`, `epic`, `chore`, `decision`

Returns:
```json
{
  "status": "success",
  "output": "Task created: agent-1 - Check weather for Tacoma WA",
  "data": {"id": "agent-1", "title": "Check weather for Tacoma WA", "status": "open", "priority": 0}
}
```

### Find Ready Work

```json
{
  "tool": "beads_task",
  "args": {
    "action": {"type": "ready"}
  }
}
```

Returns only tasks that have no open blockers — the next thing to work on.

### Claim a Task

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "update",
      "task_id": "agent-1",
      "claim": true
    }
  }
}
```

Atomically sets the assignee to the agent and status to `in_progress`. If another agent already claimed it, this fails — no double work.

### Add Dependencies

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "dep_add",
      "child_id": "agent-2",
      "parent_id": "agent-1"
    }
  }
}
```

Now `agent-2` won't show up in `ready` until `agent-1` is closed.

### Close a Task

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "close",
      "task_id": "agent-1",
      "reason": "Weather data retrieved successfully"
    }
  }
}
```

### List All Tasks

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "list",
      "status": "open"
    }
  }
}
```

Filter options: `status` (open/closed/all), `assignee`, `priority`, `limit`

### Show Task Details

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "show",
      "task_id": "agent-1"
    }
  }
}
```

### Search Tasks

```json
{
  "tool": "beads_task",
  "args": {
    "action": {
      "type": "search",
      "query": "weather"
    }
  }
}
```

### Initialize Beads

```json
{
  "tool": "beads_task",
  "args": {
    "action": {"type": "init"}
  }
}
```

Only needed if Beads hasn't been initialized in the working directory yet.

---

## Multi-Agent Coordination Example

**Scenario:** Agent A researches a topic, Agent B writes a report from the research.

```
1. Agent A creates two tasks:
   - "Research AI news" (priority 0)
   - "Write summary report" (priority 1)

2. Agent A adds a dependency:
   - "Write summary report" blocked by "Research AI news"

3. Agent A claims "Research AI news" and starts working.

4. Meanwhile, Agent B calls `ready` — only sees nothing (blocked).

5. Agent A finishes research, closes "Research AI news".

6. Agent B calls `ready` — now sees "Write summary report" (unblocked!).

7. Agent B claims it and writes the report.

8. Agent B closes "Write summary report".
```

The tasks persist even if the hub restarts between steps 5 and 6.

---

## CLI Quick Reference

You can also manage tasks from the terminal:

```bash
# List ready tasks
bd ready

# Create a task
bd create "Fix the login bug" -p 0 --type bug

# Claim a task
bd update agent-5 --claim

# Close a task
bd close agent-5 --reason "Fixed in commit abc123"

# Add dependency
bd dep add agent-6 agent-5

# Search
bd search "login"

# List everything
bd list --status all

# Show task details
bd show agent-5
```

All changes from the CLI are immediately visible to agents, and vice versa.

---

## Where Data Lives

```
/root/agent/.beads/
├── issues.jsonl    ← All tasks stored here (human-readable, git-friendly)
└── config.toml     ← Beads configuration
```

The `.beads/issues.jsonl` file is plain text — you can view, edit, or back it up like any file. It's also git-compatible if you want version control on your tasks.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "bd CLI not found" | Run `npm install -g @beads/bd` |
| "no beads database found" | Run `bd init` in your project root (`/root/agent/`) |
| Tasks not showing in agent | Make sure the hub was restarted after plugin was added |
| "CGO not available" warning | Normal — Beads falls back to JSONL-only mode, works fine |
| Agent can't claim task | Another agent already claimed it (atomic operation) |

# pmem-agent

Persistent, concurrent-safe project memory for [Claude Code](https://claude.ai/code) agents.

Stores structured project facts in `.claude/memory/project-memory.json`. Multiple agents can read and write safely — all operations go through an exclusive file lock with stale-lock detection.

## Install

### pip *(recommended — gives you `pmem` as a system command)*

```bash
pip install pmem-agent
pmem setup          # installs the Claude Code subagent to ~/.claude/agents/
```

### npx *(no install required)*

```bash
npx pmem-agent
```

### curl — Mac / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/thechandanbhagat/pmem-agent/main/install.sh | bash
```

### PowerShell — Windows

```powershell
iwr -useb https://raw.githubusercontent.com/thechandanbhagat/pmem-agent/main/install.ps1 | iex
```

### Clone and run

```bash
git clone https://github.com/thechandanbhagat/pmem-agent
cd pmem-agent
./install.sh          # Mac/Linux
./install.ps1         # Windows (PowerShell)
```

---

## Quick start

```bash
# 1. Mark your project root (run once)
cd ~/projects/my-app
pmem init-root

# 2. Write some facts
pmem write project '{"name":"my-app","type":"web-app"}'
pmem merge '{"tech_stack":{"languages":["TypeScript"],"frameworks":["React"]}}'

# 3. Read them back
pmem read
```

---

## Multi-repo / monorepo

When several git repos share a common parent folder, one `init-root` at the
parent makes all subrepos share the same memory file automatically.

```
my-project/
├── .pmem-root          ← root marker (gitignored)
├── .claude/
│   └── memory/
│       └── project-memory.json   ← shared by ALL subrepos
├── api/                ← git repo
├── web/                ← git repo
└── mobile/             ← git repo
```

```bash
cd ~/projects/my-project
pmem init-root            # one-time setup

# Now from any subrepo, pmem always hits the shared file:
cd ~/projects/my-project/api
pmem write tech_stack '{"languages":["TypeScript"]}'

cd ~/projects/my-project/web
pmem read tech_stack      # same data
```

**Env var override** (useful in CI):

```bash
export PMEM_ROOT=/path/to/my-project
pmem read
```

**Debug which file will be used:**

```bash
pmem root
# Memory path: /path/to/my-project/.claude/memory/project-memory.json
# Source:      .pmem-root marker at /path/to/my-project
```

---

## Memory schema

```json
{
  "project":      { "name": "", "description": "", "type": "", "root": "" },
  "tech_stack":   { "languages": [], "frameworks": [], "databases": [], "tools": [] },
  "architecture": { "pattern": "", "key_decisions": [] },
  "conventions":  { "naming": "", "file_org": "", "test_pattern": "" },
  "repos":        {},
  "current_goals": [],
  "known_issues":  [],
  "_last_updated": "",
  "_agents":       {}
}
```

---

## Using in Claude Code

After `pmem setup`, a `project-memory` subagent is available in Claude Code.
Spawn it at the start of any long-running task:

> "Initialize project memory" — scans manifests, README, and directory layout,
> writes structured facts to `.claude/memory/project-memory.json`.

> "Load project context" — reads memory and summarises it before you start work.

> "Remember that we decided to use Postgres instead of SQLite" — appends to
> `architecture.key_decisions`.

### Parallel agent coordination

When multiple Claude Code agents run in parallel, each registers itself on
startup and reads what peers are working on — preventing duplicate work.
The `_agents` key in memory is the coordination table; it is automatically
cleaned up when each agent finishes.

---

## CLI reference

```
pmem setup                       Install Claude Code subagent to ~/.claude/agents/
pmem init-root                   Mark cwd as project root (shared by all subrepos)
pmem root                        Show resolved memory path

pmem read [key]                  Print all memory or one top-level key
pmem write <key> <value>         Set key (value: JSON or plain string)
pmem merge <json>                Deep-merge a JSON object into memory
pmem delete <key>                Remove a top-level key
pmem reset                       Wipe all memory

pmem agent-register <id> <task>  Register a running agent
pmem agent-update <id> <status>  Update agent status
pmem agent-deregister <id>       Unregister agent on completion
```

---

## How it works

- **Storage**: plain JSON at `.claude/memory/project-memory.json`
- **Locking**: `O_CREAT|O_EXCL` on a `.lock` sidecar file — atomic on all major
  filesystems, no dependencies required
- **Stale locks**: automatically cleared after 30 s so a crashed agent never
  permanently blocks others
- **Root discovery**: walks up from cwd looking for `.pmem-root` marker or an
  existing memory file — works from any depth in a monorepo

---

## Requirements

- Python 3.10+ (stdlib only — no dependencies)
- Claude Code (for the subagent)

---

## License

MIT

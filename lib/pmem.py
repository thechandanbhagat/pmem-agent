#!/usr/bin/env python3
"""
pmem — project memory CLI
Reads/writes .claude/memory/project-memory.json (searched from cwd upward).
All operations use an exclusive lock file — safe for concurrent agent use.
"""

import contextlib
import datetime
import errno
import json
import os
import pathlib
import sys
import time

MEMORY_FILENAME = pathlib.Path(".claude") / "memory" / "project-memory.json"
ROOT_MARKER = ".pmem-root"
LOCK_RETRIES = 20
LOCK_RETRY_S = 0.1
STALE_LOCK_AGE_S = 30.0


# ── path helpers ─────────────────────────────────────────────────────────────

def find_memory_path() -> pathlib.Path:
    """
    Resolution order (first match wins):
      1. $PMEM_ROOT env var  — explicit override, e.g. for CI scripts
      2. .pmem-root marker   — walk up; the dir containing .pmem-root is root
      3. .claude/project-memory.json — walk up; use first existing file found
      4. Fallback: cwd/.claude/project-memory.json (new file will be created here)
    """
    # 1. Explicit env override
    env_root = os.environ.get("PMEM_ROOT")
    if env_root:
        return pathlib.Path(env_root).expanduser().resolve() / MEMORY_FILENAME

    cwd = pathlib.Path.cwd()
    d = cwd
    first_existing_memory: pathlib.Path | None = None

    while True:
        # 2. .pmem-root marker — explicit project root declaration
        if (d / ROOT_MARKER).exists():
            return d / MEMORY_FILENAME

        # 3. Existing memory file — implicit root (remember first one found)
        candidate = d / MEMORY_FILENAME
        if first_existing_memory is None and candidate.exists():
            first_existing_memory = candidate

        parent = d.parent
        if parent == d:
            break
        d = parent

    # 4. Fallback
    return first_existing_memory or (cwd / MEMORY_FILENAME)


def lock_path(data: pathlib.Path) -> pathlib.Path:
    return data.parent / (data.name + ".lock")


# ── locking (atomic O_CREAT|O_EXCL, stale-lock aware) ────────────────────────

@contextlib.contextmanager
def exclusive_lock(data_path: pathlib.Path):
    lp = lock_path(data_path)
    lp.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(LOCK_RETRIES):
        try:
            fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            break
        except OSError as e:
            if e.errno not in (errno.EEXIST, errno.EACCES):
                raise
            # Stale lock detection: if lock file is old, remove it and retry.
            try:
                age = time.time() - lp.stat().st_mtime
                if age > STALE_LOCK_AGE_S:
                    lp.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if attempt < LOCK_RETRIES - 1:
                time.sleep(LOCK_RETRY_S)
            else:
                raise RuntimeError(
                    f"Lock timeout after {LOCK_RETRIES * LOCK_RETRY_S:.1f}s — "
                    "another agent may be stuck. Delete "
                    f"{lp} if the process is gone."
                )
    try:
        yield
    finally:
        lp.unlink(missing_ok=True)


# ── data helpers ─────────────────────────────────────────────────────────────

def ensure_data_file(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}", encoding="utf-8")


def read_data(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Memory file contains invalid JSON ({e}). Run `pmem reset` to clear it."
        ) from None


def write_data(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deep_merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_read(key: str | None) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    with exclusive_lock(path):
        data = read_data(path)
    out = data.get(key) if key else data
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_write(key: str, raw: str) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    with exclusive_lock(path):
        data = read_data(path)
        data[key] = value
        data["_last_updated"] = now_iso()
        write_data(path, data)


def cmd_merge(raw: str) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    try:
        patch = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"merge argument must be valid JSON: {e}") from None
    if not isinstance(patch, dict):
        raise ValueError("merge argument must be a JSON object")
    with exclusive_lock(path):
        data = read_data(path)
        deep_merge(data, patch)
        data["_last_updated"] = now_iso()
        write_data(path, data)


def cmd_delete(key: str) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    with exclusive_lock(path):
        data = read_data(path)
        data.pop(key, None)
        data["_last_updated"] = now_iso()
        write_data(path, data)


def cmd_reset() -> None:
    path = find_memory_path()
    ensure_data_file(path)
    with exclusive_lock(path):
        write_data(path, {})


def cmd_agent_register(agent_id: str, task: str) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    now = now_iso()
    patch = {"_agents": {agent_id: {"task": task, "status": "running",
                                     "started_at": now, "updated_at": now}}}
    with exclusive_lock(path):
        data = read_data(path)
        deep_merge(data, patch)
        write_data(path, data)


def cmd_agent_update(agent_id: str, status: str) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    patch = {"_agents": {agent_id: {"status": status, "updated_at": now_iso()}}}
    with exclusive_lock(path):
        data = read_data(path)
        deep_merge(data, patch)
        write_data(path, data)


def cmd_agent_deregister(agent_id: str) -> None:
    path = find_memory_path()
    ensure_data_file(path)
    with exclusive_lock(path):
        data = read_data(path)
        agents = data.get("_agents", {})
        agents.pop(agent_id, None)
        if agents:
            data["_agents"] = agents
        else:
            data.pop("_agents", None)
        write_data(path, data)


def _add_to_gitignore(cwd: pathlib.Path, entry: str) -> bool:
    """Append entry to .gitignore if not already present. Returns True if added."""
    gitignore = cwd / ".gitignore"
    if gitignore.exists():
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        if any(line.strip() == entry for line in lines):
            return False
        # Ensure file ends with a newline before appending
        existing = gitignore.read_text(encoding="utf-8")
        suffix = "" if existing.endswith("\n") else "\n"
        gitignore.write_text(existing + suffix + entry + "\n", encoding="utf-8")
    else:
        gitignore.write_text(entry + "\n", encoding="utf-8")
    return True


def cmd_init_root() -> None:
    """Mark cwd as the project root so all subrepos share this memory file."""
    cwd = pathlib.Path.cwd()
    marker = cwd / ROOT_MARKER
    marker.write_text(
        "# pmem project root — all subdirectories (subrepos included) share\n"
        "# .claude/project-memory.json in this directory.\n"
        "# Delete this file to revert to per-directory memory discovery.\n",
        encoding="utf-8",
    )
    memory = cwd / MEMORY_FILENAME
    ensure_data_file(memory)

    added = _add_to_gitignore(cwd, ROOT_MARKER)
    gitignore_note = f"Added to .gitignore" if added else "Already in .gitignore"

    print(f"Project root set: {cwd}")
    print(f"Shared memory:    {memory}")
    print(f"Marker:           {marker}  ({gitignore_note})")
    print()
    print("All `pmem` calls from any subdirectory will now use the shared file.")


def cmd_root() -> None:
    """Print the resolved memory file path (useful for debugging multi-repo setups)."""
    path = find_memory_path()
    source = "env:PMEM_ROOT"
    if not os.environ.get("PMEM_ROOT"):
        d = pathlib.Path.cwd()
        source = "fallback (cwd)"
        while True:
            if (d / ROOT_MARKER).exists():
                source = f".pmem-root marker at {d}"
                break
            if (d / MEMORY_FILENAME).exists():
                source = f"existing memory file"
                break
            parent = d.parent
            if parent == d:
                break
            d = parent
    print(f"Memory path: {path}")
    print(f"Source:      {source}")
    print(f"Exists:      {path.exists()}")


# ── CLI entry point ───────────────────────────────────────────────────────────

USAGE = """\
pmem — project memory CLI
  Reads/writes .claude/project-memory.json (searched from cwd upward).
  All operations are file-locked — safe for concurrent agent use.

ROOT RESOLUTION (first match wins):
  1. $PMEM_ROOT env var
  2. .pmem-root marker file (walk up from cwd)
  3. Existing .claude/project-memory.json (walk up from cwd)
  4. Fallback: cwd/.claude/project-memory.json

COMMANDS:
  init-root                   Mark cwd as project root (shared by all subrepos)
  root                        Show resolved memory path (debug multi-repo issues)
  read [key]                  Print all memory or a single top-level key
  write <key> <value>         Set key (value: JSON or plain string)
  merge <json>                Deep-merge a JSON object into memory
  delete <key>                Remove a top-level key
  reset                       Wipe all memory
  agent-register <id> <task>  Register a running agent
  agent-update <id> <status>  Update agent status
  agent-deregister <id>       Unregister agent on completion
"""


def main() -> int:
    args = sys.argv[1:]
    try:
        match args:
            case ["init-root"]:
                cmd_init_root()
            case ["root"]:
                cmd_root()
            case ["read"]:
                cmd_read(None)
            case ["read", key]:
                cmd_read(key)
            case ["write", key, value]:
                cmd_write(key, value)
            case ["merge", patch]:
                cmd_merge(patch)
            case ["delete", key]:
                cmd_delete(key)
            case ["reset"]:
                cmd_reset()
            case ["agent-register", aid, task]:
                cmd_agent_register(aid, task)
            case ["agent-update", aid, status]:
                cmd_agent_update(aid, status)
            case ["agent-deregister", aid]:
                cmd_agent_deregister(aid)
            case _:
                print(USAGE, file=sys.stderr)
                return 1
    except (RuntimeError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

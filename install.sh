#!/usr/bin/env bash
# pmem-agent installer — https://github.com/thechandanbhagat/pmem-agent
set -euo pipefail

REPO="thechandanbhagat/pmem-agent"
BRANCH="main"
BASE="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
CLAUDE_BIN="$HOME/.claude/bin"
CLAUDE_AGENTS="$HOME/.claude/agents"

echo "Installing pmem-agent..."
mkdir -p "$CLAUDE_BIN" "$CLAUDE_AGENTS"

# Prefer curl, fall back to wget
download() { curl -fsSL "$1" -o "$2" 2>/dev/null || wget -q "$1" -O "$2"; }

download "${BASE}/src/pmem_agent/cli.py" "$CLAUDE_BIN/pmem.py"
download "${BASE}/agents/project-memory.md" "$CLAUDE_AGENTS/project-memory.md"

# Shell wrapper so `pmem` works without specifying python3 each time
cat > "$CLAUDE_BIN/pmem" <<'WRAPPER'
#!/bin/sh
exec python3 "$(dirname "$0")/pmem.py" "$@"
WRAPPER
chmod +x "$CLAUDE_BIN/pmem"

# Add ~/.claude/bin to PATH in shell rc files (best-effort, skips if already present)
PATH_LINE='export PATH="$HOME/.claude/bin:$PATH"  # pmem-agent'
for RC in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$RC" ] && ! grep -q '.claude/bin' "$RC"; then
        printf '\n%s\n' "$PATH_LINE" >> "$RC"
        echo "  Added ~/.claude/bin to PATH in $RC"
    fi
done

echo ""
echo "pmem-agent installed!"
echo "  CLI:   $CLAUDE_BIN/pmem"
echo "  Agent: $CLAUDE_AGENTS/project-memory.md"
echo ""
echo "Restart your shell, then run in your project:"
echo "  pmem init-root"

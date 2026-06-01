#!/usr/bin/env node
// npx pmem-agent — installs pmem CLI and Claude Code subagent
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

const HOME = os.homedir();
const IS_WINDOWS = process.platform === 'win32';
const CLAUDE_BIN = path.join(HOME, '.claude', 'bin');
const CLAUDE_AGENTS = path.join(HOME, '.claude', 'agents');

const LIB = path.join(__dirname, '..', 'lib');
const SRC_PY = path.join(LIB, 'pmem.py');
const SRC_AGENT = path.join(LIB, 'project-memory.md');

function ensureDir(d) { fs.mkdirSync(d, { recursive: true }); }

function checkPython() {
  for (const cmd of ['python3', 'python']) {
    try {
      const out = execSync(`${cmd} -c "import sys; assert sys.version_info >= (3,10)"`,
        { stdio: 'pipe' });
      return cmd;
    } catch {}
  }
  console.error('Error: Python 3.10+ is required. Install from https://python.org');
  process.exit(1);
}

function addToPath(dir) {
  if (IS_WINDOWS) {
    try {
      execSync(
        `powershell -Command "[Environment]::SetEnvironmentVariable('PATH', '${dir};' + [Environment]::GetEnvironmentVariable('PATH','User'), 'User')"`,
        { stdio: 'pipe' }
      );
      return true;
    } catch { return false; }
  }
  // Unix: append to rc files if not already present
  const line = `\nexport PATH="$HOME/.claude/bin:$PATH"  # pmem-agent`;
  let added = false;
  for (const rc of ['.bashrc', '.zshrc', '.profile']) {
    const rcPath = path.join(HOME, rc);
    if (!fs.existsSync(rcPath)) continue;
    const content = fs.readFileSync(rcPath, 'utf8');
    if (!content.includes('.claude/bin')) {
      fs.appendFileSync(rcPath, line, 'utf8');
      added = true;
    }
  }
  return added;
}

function install() {
  const python = checkPython();

  ensureDir(CLAUDE_BIN);
  ensureDir(CLAUDE_AGENTS);

  // Copy CLI
  fs.copyFileSync(SRC_PY, path.join(CLAUDE_BIN, 'pmem.py'));

  // Create platform wrapper
  if (IS_WINDOWS) {
    fs.writeFileSync(
      path.join(CLAUDE_BIN, 'pmem.bat'),
      `@echo off\n${python} "%~dp0pmem.py" %*\n`,
      'utf8'
    );
  } else {
    const wrapper = path.join(CLAUDE_BIN, 'pmem');
    fs.writeFileSync(wrapper, `#!/bin/sh\nexec ${python} "$(dirname "$0")/pmem.py" "$@"\n`, 'utf8');
    fs.chmodSync(wrapper, 0o755);
  }

  // Copy agent definition
  fs.copyFileSync(SRC_AGENT, path.join(CLAUDE_AGENTS, 'project-memory.md'));

  // PATH
  const pathUpdated = addToPath(CLAUDE_BIN);

  console.log('\npmem-agent installed!');
  console.log(`  CLI:   ${path.join(CLAUDE_BIN, IS_WINDOWS ? 'pmem.bat' : 'pmem')}`);
  console.log(`  Agent: ${path.join(CLAUDE_AGENTS, 'project-memory.md')}`);
  if (pathUpdated) {
    console.log(`\n  ~/.claude/bin added to PATH — restart your shell to use 'pmem'`);
  }
  console.log('\nNext: cd into your project and run:');
  console.log('  pmem init-root');
}

install();

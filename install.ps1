# pmem-agent installer — https://github.com/thechandanbhagat/pmem-agent
$ErrorActionPreference = 'Stop'

$Repo   = "thechandanbhagat/pmem-agent"
$Branch = "main"
$Base   = "https://raw.githubusercontent.com/$Repo/$Branch"

$ClaudeBin    = "$env:USERPROFILE\.claude\bin"
$ClaudeAgents = "$env:USERPROFILE\.claude\agents"

Write-Host "Installing pmem-agent..."
New-Item -ItemType Directory -Force $ClaudeBin    | Out-Null
New-Item -ItemType Directory -Force $ClaudeAgents | Out-Null

Invoke-WebRequest -Uri "$Base/src/pmem_agent/cli.py"          -OutFile "$ClaudeBin\pmem.py"
Invoke-WebRequest -Uri "$Base/agents/project-memory.md"       -OutFile "$ClaudeAgents\project-memory.md"

# .bat wrapper so `pmem` works from any shell on Windows
"@echo off`npython `"%~dp0pmem.py`" %*" | Set-Content "$ClaudeBin\pmem.bat" -Encoding UTF8

# Add ~/.claude/bin to the user PATH (permanent, current session picks it up on restart)
$CurrentPath = [Environment]::GetEnvironmentVariable('PATH', 'User') ?? ''
if ($CurrentPath -notlike "*$ClaudeBin*") {
    [Environment]::SetEnvironmentVariable('PATH', "$ClaudeBin;$CurrentPath", 'User')
    Write-Host "  Added $ClaudeBin to user PATH"
}

Write-Host ""
Write-Host "pmem-agent installed!"
Write-Host "  CLI:   $ClaudeBin\pmem.bat"
Write-Host "  Agent: $ClaudeAgents\project-memory.md"
Write-Host ""
Write-Host "Restart your shell, then run in your project:"
Write-Host "  pmem init-root"

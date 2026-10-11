# Nightly run: Claude Code processes the day's recordings with the "recordings" skill, unattended.
# Registered in Task Scheduler by register_nightly.ps1. Log: nightly\nightly.log (next to this file).
#
# Lessons that cost real days of silent failure:
#  - chcp 65001 + UTF-8 output BEFORE running claude, otherwise Hebrew in the log turns into garbage.
#  - This file is ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.
#  - Task Scheduler reports "success" even when nothing was done. Check the log, not the scheduler.

param([string]$Workspace = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))))

chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$log = Join-Path $PSScriptRoot "nightly.log"
Set-Location $Workspace

"===== $(Get-Date -Format s) start (workspace: $Workspace)" | Out-File $log -Append -Encoding utf8
& claude -p "/recordings nightly" --model sonnet 2>&1 | Out-File $log -Append -Encoding utf8
"===== $(Get-Date -Format s) end, exit=$LASTEXITCODE" | Out-File $log -Append -Encoding utf8

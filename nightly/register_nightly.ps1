# Registers the nightly run in Windows Task Scheduler (current user, no admin needed).
#   powershell -ExecutionPolicy Bypass -File nightly\register_nightly.ps1 -At 02:00
# "Wake to run" wakes a sleeping computer. A computer that is shut down will not run - it catches up
# on the next start (StartWhenAvailable).
# ASCII only on purpose (Windows PowerShell 5.1 + UTF-8 without BOM).

param([string]$At = "02:00", [string]$TaskName = "Recordings kit - nightly")

$script = Join-Path $PSScriptRoot "run_nightly.ps1"
# -EncodedCommand instead of -File: with a non-English path (e.g. Google Drive "My Drive" in Hebrew)
# "powershell -File <path>" fails silently. The encoded (UTF-16) command carries any path safely.
$enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("& '$($script.Replace("'", "''"))'"))
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $enc"
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State

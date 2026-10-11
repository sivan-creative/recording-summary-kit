# Silent capture of an online video / recorded lesson that cannot be downloaded.
# While it runs, ALL computer sound goes into a virtual cable instead of the speakers (so nobody hears it,
# e.g. at night), and ffmpeg records the cable. At the end the normal speakers are restored, even on error.
# Transcription happens afterwards: python scripts/transcribe.py --file "<OutFile>"
#
# Run detached (a capture can take hours). Use -EncodedCommand, not -File: with a non-English path
# (e.g. Google Drive "My Drive" in Hebrew) "powershell -File <path>" fails silently, without any error.
#   $cmd = "& '<kit>\scripts\capture_online.ps1' -DurationSeconds 5400 -OutFile '<path>.m4a'"
#   $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$enc
#
# Needs: ffmpeg, VB-CABLE (or Voicemeeter), PowerShell module AudioDeviceCmdlets. See docs/online-video.md.
# This file is ASCII only on purpose: Windows PowerShell 5.1 misreads UTF-8 files without a BOM.

param(
    [Parameter(Mandatory=$true)][int]$DurationSeconds,
    [Parameter(Mandatory=$true)][string]$OutFile,
    [string]$PlaybackDevice = "CABLE Input",                                # where Windows sends the sound
    [string]$CaptureDevice = "CABLE Output (VB-Audio Virtual Cable)",       # what ffmpeg records
    [string]$LogFile = "$OutFile.log"
)

Import-Module AudioDeviceCmdlets
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'

$previous = Get-AudioDevice -Playback
$cable = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' -and $_.Name -like "*$PlaybackDevice*" } | Select-Object -First 1
if (-not $cable) { "ERROR: playback device '$PlaybackDevice' not found" | Out-File $LogFile; exit 1 }

try {
    # keep the computer awake for the whole capture without touching the power settings
    [Win32.Power]::SetThreadExecutionState([uint32]"0x80000001") | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    Set-AudioDevice -ID $cable.ID | Out-Null
    "capture start $(Get-Date -Format s) device=$CaptureDevice duration=$DurationSeconds previous=$($previous.Name)" | Out-File $LogFile
    & ffmpeg -hide_banner -y -f dshow -i "audio=$CaptureDevice" -t $DurationSeconds -ac 1 -ar 16000 -c:a aac -b:a 64k $OutFile 2>> $LogFile
    "capture end $(Get-Date -Format s) exit=$LASTEXITCODE" | Out-File $LogFile -Append
}
finally {
    Set-AudioDevice -ID $previous.ID | Out-Null
    [Win32.Power]::SetThreadExecutionState([uint32]"0x80000000") | Out-Null   # back to normal sleep rules
    "speakers restored: $($previous.Name)" | Out-File $LogFile -Append
}

"""What is already installed on this computer and what is missing. Read-only - changes nothing.

Run it first (and again after every install step):
    python scripts/check_setup.py
Prints one line per item: OK / MISSING / OPTIONAL-MISSING, with a short hint.
Can run with any Python 3.10+ even before the kit's packages are installed.
"""
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
rows = []


def row(status: str, item: str, detail: str = "") -> None:
    rows.append((status, item, detail))


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    row("OK", "system", f"{platform.system()} {platform.release()}, Python {platform.python_version()}")
    if sys.version_info < (3, 10):
        row("MISSING", "python 3.10+", "install: winget install Python.Python.3.12")

    ff = shutil.which("ffmpeg")
    row("OK" if ff else "MISSING", "ffmpeg", ff or "install: winget install Gyan.FFmpeg (then open a new terminal)")

    gpu = run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    row("OK" if gpu else "OPTIONAL-MISSING", "NVIDIA GPU",
        gpu or "no NVIDIA card - transcription runs on the CPU (works, about 5-15x slower)")

    for mod, pip_name, needed in [
        ("faster_whisper", "faster-whisper", True),
        ("keyring", "keyring", True),
        ("nvidia.cublas", "nvidia-cublas-cu12", bool(gpu)),
        ("nvidia.cudnn", "nvidia-cudnn-cu12", bool(gpu)),
        ("pyannote.audio", "pyannote.audio", False),
        ("torch", "torch", False),
    ]:
        try:
            found = importlib.util.find_spec(mod) is not None
        except ModuleNotFoundError:
            found = False
        status = "OK" if found else ("MISSING" if needed else "OPTIONAL-MISSING")
        row(status, f"python package {pip_name}", "" if found else f"pip install {pip_name}")

    if importlib.util.find_spec("torch"):
        import torch
        row("OK" if torch.cuda.is_available() or not gpu else "MISSING", "torch sees the GPU",
            f"torch {torch.__version__}, cuda={torch.cuda.is_available()}"
            + ("" if torch.cuda.is_available() or not gpu else
               " - reinstall: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128"))

    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    model_dir = cache / "models--ivrit-ai--whisper-large-v3-turbo-ct2"
    row("OK" if model_dir.exists() else "MISSING", "Hebrew Whisper model (ivrit.ai, ~1.6GB)",
        str(model_dir) if model_dir.exists() else "downloads automatically on the first transcription")

    if importlib.util.find_spec("keyring"):
        import keyring
        for name, why in [("HF_TOKEN", "speaker separation"), ("MONDAY_API_TOKEN", "monday summaries")]:
            row("OK" if keyring.get_password("recordings-kit", name) else "OPTIONAL-MISSING",
                f"secret {name}", f"needed only for {why}")

    cfg_path = KIT / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        row("OK", "config.json", str(cfg_path))
        for key in ("phone_inbox", "recordings_root", "zoom_inbox", "zoom_archive", "transcripts_root"):
            p = cfg.get(key)
            if p:
                p = Path(os.path.expandvars(os.path.expanduser(p)))
                row("OK" if p.exists() else "MISSING", f"folder {key}", str(p))
    else:
        row("MISSING", "config.json", "created during setup from config.example.json")

    if platform.system() == "Windows":
        drives = [f"{d}:\\" for d in "DEFGHIJ" if Path(f"{d}:\\My Drive").exists() or Path(f"{d}:\\האחסון שלי").exists()]
        row("OK" if drives else "OPTIONAL-MISSING", "Google Drive for desktop",
            ", ".join(drives) or "not found - needed only if transcripts/recordings should be backed up to Drive")
        zoom = next((p for p in [Path(os.environ.get("APPDATA", "")) / "Zoom" / "bin" / "Zoom.exe",
                                 Path(os.environ.get("ProgramFiles", "")) / "Zoom" / "bin" / "Zoom.exe",
                                 Path(os.environ.get("ProgramFiles(x86)", "")) / "Zoom" / "bin" / "Zoom.exe"]
                     if p.exists()), None)
        row("OK" if zoom else "OPTIONAL-MISSING", "Zoom desktop app", str(zoom) if zoom else
            "local recording needs the desktop app (not Zoom in the browser)")
        devices = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace").stderr if ff else ""
        cable = "CABLE Output" in devices
        vm = "Voicemeeter Out B1" in devices
        row("OK" if cable or vm else "OPTIONAL-MISSING", "virtual audio cable (silent capture of online videos)",
            "VB-CABLE" if cable else "Voicemeeter" if vm else "install VB-CABLE - see docs/online-video.md")
        adc = run(["powershell", "-NoProfile", "-Command",
                   "Get-Module -ListAvailable AudioDeviceCmdlets | Select -First 1 -Expand Name"])
        row("OK" if adc else "OPTIONAL-MISSING", "PowerShell AudioDeviceCmdlets", "" if adc else
            "Install-Module AudioDeviceCmdlets -Scope CurrentUser (switches the sound output during capture)")
    node = shutil.which("node")
    row("OK" if node else "OPTIONAL-MISSING", "Node.js", node or "needed only for the browser (Playwright MCP): winget install OpenJS.NodeJS.LTS")
    # on Windows "claude" is a .cmd/.ps1 shim that subprocess cannot start directly, so only locate it
    claude = shutil.which("claude")
    row("OK" if claude else "MISSING", "Claude Code CLI", claude or "needed for the nightly run")

    width = max(len(r[1]) for r in rows)
    for status, item, detail in rows:
        print(f"{status:17} {item:{width}}  {detail}")


if __name__ == "__main__":
    main()

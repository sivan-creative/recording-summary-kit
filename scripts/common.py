"""Shared helpers for the recordings kit: config, Whisper model (GPU or CPU), secrets, index.

Every script in this folder reads ../config.json (created during setup from config.example.json).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
CONFIG_PATH = KIT / "config.json"
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".amr", ".3gp", ".ogg", ".aac", ".opus", ".flac", ".mp4"}
KEYRING_SERVICE = "recordings-kit"

# NVIDIA libraries installed from pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) are not on PATH by default.
# Without this, faster-whisper on the GPU fails with "cublas64_12.dll not found".
for _mod in ("nvidia.cublas", "nvidia.cudnn"):
    try:
        _pkg = __import__(_mod, fromlist=["_"])
        _bin = os.path.join(list(_pkg.__path__)[0], "bin")
        if os.path.isdir(_bin):
            os.add_dll_directory(_bin)
            os.environ["PATH"] = _bin + os.pathsep + os.environ["PATH"]
    except ImportError:
        pass


def utf8_console() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Missing {CONFIG_PATH}. Copy config.example.json to config.json and fill it in.")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for key in ("phone_inbox", "recordings_root", "zoom_inbox", "zoom_archive", "transcripts_root"):
        if cfg.get(key):
            cfg[key] = Path(os.path.expandvars(os.path.expanduser(cfg[key])))
    return cfg


def load_model(cfg: dict):
    """Whisper model on the GPU if there is a working NVIDIA card, otherwise on the CPU (slower, same quality)."""
    from faster_whisper import WhisperModel
    name = cfg.get("model", "ivrit-ai/whisper-large-v3-turbo-ct2")
    device = cfg.get("device", "auto")
    if device in ("auto", "cuda"):
        try:
            model = WhisperModel(name, device="cuda", compute_type="float16")
            print("whisper: GPU", flush=True)
            return model
        except Exception as e:  # no NVIDIA card, old driver or missing CUDA libraries
            if device == "cuda":
                raise
            print(f"whisper: GPU not available ({type(e).__name__}), using CPU", flush=True)
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe_lines(model, path: Path, language: str = "he") -> list[tuple[float, float, str]]:
    segments, _ = model.transcribe(str(path), language=language, vad_filter=True, beam_size=5)
    out = []
    for s in segments:
        text = s.text.strip()
        # Whisper "hallucinates" the same sentence again and again over silence or music - keep it once
        if text and not (len(out) >= 2 and out[-1][2] == text and out[-2][2] == text):
            out.append((s.start, s.end, text))
    return out


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def fmt(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def get_secret(name: str) -> str:
    import keyring
    value = keyring.get_password(KEYRING_SERVICE, name)
    if not value:
        raise SystemExit(f"{name} is not saved yet. Run: python scripts/secrets_store.py set {name}")
    return value


class Index:
    """transcripts_root/index.json - one entry per recording: where its transcript is, duration, old name."""

    def __init__(self, cfg: dict):
        self.path = cfg["transcripts_root"] / "index.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

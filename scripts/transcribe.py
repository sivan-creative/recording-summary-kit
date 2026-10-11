"""Transcribe new phone / voice-recorder recordings (or one specific file) with Hebrew Whisper (ivrit.ai).

Reads the phone inbox from config.json (the folder the phone app uploads to, e.g. Call / Voice Recorder).
Writes transcripts_root/<parent folder>/<file name>.txt, one line per sentence: "[mm:ss] text".
A recording that already has a transcript is skipped, so it is safe to run again and again.

Usage:
    python scripts/transcribe.py                 # everything new in the phone inbox
    python scripts/transcribe.py --file "<path>" # one file anywhere (online lesson capture, a file someone sent)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import AUDIO_EXT, Index, duration, fmt, load_config, load_model, transcribe_lines, utf8_console


def target_for(cfg: dict, p: Path) -> Path:
    return cfg["transcripts_root"] / p.parent.name / f"{p.stem}.txt"


def main() -> None:
    utf8_console()
    cfg = load_config()
    if sys.argv[1:2] == ["--file"]:
        files = [Path(sys.argv[2])]
    else:
        inbox = cfg["phone_inbox"]
        files = sorted(p for p in inbox.rglob("*") if p.suffix.lower() in AUDIO_EXT and not p.name.startswith("~"))
    todo = [p for p in files if not target_for(cfg, p).exists()]
    print(f"{len(files)} recordings, {len(todo)} to transcribe", flush=True)
    if not todo:
        return

    model = load_model(cfg)
    index = Index(cfg)
    for i, p in enumerate(todo, 1):
        t0, dur = time.time(), duration(p)
        lines = transcribe_lines(model, p, cfg.get("language", "he"))
        target = target_for(cfg, p)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(f"[{fmt(a)}] {t}" for a, _, t in lines), encoding="utf-8")
        index.data[f"{p.parent.name}/{p.name}"] = {"duration_sec": round(dur), "transcript": str(target), "source": str(p)}
        index.save()
        print(f"[{i}/{len(todo)}] {p.name} | {fmt(dur)} of audio in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

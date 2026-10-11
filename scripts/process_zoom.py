"""Zoom local recordings: a transcript with the speaker's name taken from each participant's own audio file.

Zoom (desktop app, local recording) saves every meeting to its own folder in zoom_inbox, e.g.
"2026-10-12 10.00.23 <meeting topic>", with video, a mixed audio file and - when "Record separate
participant audio files" is on - an "Audio Record" sub-folder with one file per participant
(audio<Name><digits>.m4a).

Usage:
    python scripts/process_zoom.py          # transcribe every finished meeting that has no transcript yet
    python scripts/process_zoom.py list     # state of each meeting in the inbox
    python scripts/process_zoom.py file "<meeting folder>" "<topic folder>" "<new name without extension>"

Transcript: transcripts_root/zoom/<meeting folder name>.txt, lines "[mm:ss] Name: text".
No per-participant files (someone else hosted, or the setting is off) -> mixed audio + diarize.py.
"file" moves the meeting to zoom_archive/<topic>/<name>.mp4/.m4a (participant files in a sub-folder)
and the transcript to transcripts_root/zoom/<topic>/<name>.txt.
"""
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import Index, duration, fmt, load_config, load_model, transcribe_lines, utf8_console

SETTLE_MIN = 10  # a meeting with a file changed in the last minutes is still being converted / written


def tr_root(cfg: dict) -> Path:
    return cfg["transcripts_root"] / "zoom"


def meetings(cfg: dict) -> list[Path]:
    inbox = cfg["zoom_inbox"]
    return sorted(p for p in inbox.iterdir() if p.is_dir()) if inbox.exists() else []


def state(cfg: dict, m: Path) -> str:
    files = [f for f in m.rglob("*") if f.is_file()]
    if any(f.suffix == ".zoom" for f in files):
        return "converting"  # Zoom has not converted yet (or conversion failed - double-click the .zoom file)
    if not any(f.suffix in (".m4a", ".mp4") for f in files):
        return "empty"
    if time.time() - max(f.stat().st_mtime for f in files) < SETTLE_MIN * 60:
        return "writing"
    return "done" if (tr_root(cfg) / f"{m.name}.txt").exists() else "ready"


def main_audio(m: Path) -> Path | None:
    for pattern in ("*.m4a", "*.mp4"):
        found = sorted(m.glob(pattern), key=lambda f: f.stat().st_size, reverse=True)
        if found:
            return found[0]
    return None


def participant_name(f: Path) -> str:
    # audioDana Cohen11234567890.m4a -> Dana Cohen
    name = re.sub(r"^audio", "", f.stem)
    name = re.sub(r"_?\d{6,}$", "", name).strip(" _-")
    return name or f.stem


def transcribe_meeting(cfg: dict, model, m: Path) -> None:
    tracks = sorted((m / "Audio Record").glob("*.m4a")) if (m / "Audio Record").exists() else []
    mixed = main_audio(m)
    target = tr_root(cfg) / f"{m.name}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    meta = {"folder": str(m), "duration_sec": round(duration(mixed)) if mixed else 0}

    if tracks:
        lines, talk = [], {}
        for f in tracks:
            who = participant_name(f)
            for a, b, text in transcribe_lines(model, f, cfg.get("language", "he")):
                lines.append((a, f"[{fmt(a)}] {who}: {text}"))
                talk[who] = talk.get(who, 0) + b - a
            if duration(f) < meta["duration_sec"] - 60:
                print(f"  warning: {f.name} is shorter than the meeting - check that lines are in the right order",
                      flush=True)
        lines.sort(key=lambda x: x[0])
        target.write_text("\n".join(t for _, t in lines), encoding="utf-8")
        meta.update({"mode": "per-participant", "speakers_sec": {k: round(v) for k, v in talk.items()}})
    else:
        subprocess.run([sys.executable, str(Path(__file__).parent / "diarize.py"), str(mixed)], check=True)
        produced = cfg["transcripts_root"] / mixed.parent.name / f"{mixed.stem}.speakers.txt"
        shutil.move(str(produced), str(target))
        if not any(produced.parent.iterdir()):
            produced.parent.rmdir()
        meta["mode"] = "diarized"

    index = Index(cfg)
    index.data[f"zoom/{m.name}"] = {**meta, "transcript": str(target)}
    index.save()
    print(f"{m.name} | {meta['mode']} | {fmt(meta['duration_sec'])} in {time.time() - t0:.0f}s -> {target}", flush=True)


def file_meeting(cfg: dict, m: Path, topic: str, base: str) -> None:
    dest = cfg["zoom_archive"] / topic
    dest.mkdir(parents=True, exist_ok=True)
    name, n = base, 1
    while any(dest.glob(f"{name}.*")):
        n += 1
        name = f"{base} ({n})"

    # the biggest file of each kind gets the clean name; extra ones (e.g. a separate screen share) keep their own
    for suffix in (".mp4", ".m4a"):
        for i, f in enumerate(sorted(m.glob(f"*{suffix}"), key=lambda f: f.stat().st_size, reverse=True)):
            shutil.move(str(f), str(dest / f"{name}{'' if i == 0 else ' - ' + f.stem}{suffix}"))
    for f in m.glob("*.txt"):
        if f.stat().st_size:
            shutil.move(str(f), str(dest / f"{name} - chat.txt"))
    if (m / "Audio Record").exists():
        shutil.move(str(m / "Audio Record"), str(dest / f"{name} - per participant audio"))

    (tr_root(cfg) / topic).mkdir(parents=True, exist_ok=True)
    old, new = tr_root(cfg) / f"{m.name}.txt", tr_root(cfg) / topic / f"{name}.txt"
    if old.exists():
        shutil.move(str(old), str(new))
    index = Index(cfg)
    entry = index.data.pop(f"zoom/{m.name}", {})
    entry.update({"transcript": str(new), "old_name": m.name, "folder": str(dest)})
    index.data[f"zoom/{topic}/{name}"] = entry
    index.save()

    leftovers = [f for f in m.rglob("*") if f.is_file() and f.suffix != ".conf" and f.stat().st_size]
    if leftovers:
        print(f"  left in the inbox (not moved): {[f.name for f in leftovers]}")
    else:
        shutil.rmtree(m)
    print(f"OK {m.name} -> {dest / name}")


def main() -> None:
    utf8_console()
    cfg = load_config()
    args = sys.argv[1:]
    if args[:1] == ["list"]:
        for m in meetings(cfg):
            print(f"{state(cfg, m):10} {m.name}")
        return
    if args[:1] == ["file"]:
        file_meeting(cfg, Path(args[1]), args[2], args[3])
        return

    todo = [m for m in meetings(cfg) if state(cfg, m) == "ready"]
    print(f"{len(meetings(cfg))} meetings in the inbox, {len(todo)} to transcribe", flush=True)
    if todo:
        model = load_model(cfg)
        for m in todo:
            transcribe_meeting(cfg, model, m)


if __name__ == "__main__":
    main()

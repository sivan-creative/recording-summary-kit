"""File a processed phone / recorder recording: new readable name + move to a topic folder,
together with its transcripts (.txt and .speakers.txt), and update index.json.

Usage:
    python scripts/file_recording.py "<recording path>" "<topic folder>" "<new name without extension>"
Topic folders come from config.json ("topics"); a new folder is created if needed.
If the name is taken, (2), (3)... is added.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import Index, load_config, utf8_console


def main() -> None:
    utf8_console()
    cfg = load_config()
    src, topic, base = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    root, tr = cfg["recordings_root"], cfg["transcripts_root"]
    (root / topic).mkdir(parents=True, exist_ok=True)
    (tr / topic).mkdir(parents=True, exist_ok=True)
    name, n = base, 1
    while (root / topic / f"{name}{src.suffix}").exists():
        n += 1
        name = f"{base} ({n})"
    dest = root / topic / f"{name}{src.suffix}"
    shutil.move(str(src), str(dest))

    for suffix in (".txt", ".speakers.txt"):
        old = tr / src.parent.name / f"{src.stem}{suffix}"
        if old.exists():
            shutil.move(str(old), str(tr / topic / f"{name}{suffix}"))

    index = Index(cfg)
    entry = index.data.pop(f"{src.parent.name}/{src.name}", {})
    entry.update({"transcript": str(tr / topic / f"{name}.txt"), "old_name": src.name, "source": str(dest)})
    index.data[f"{topic}/{dest.name}"] = entry
    index.save()
    print(f"OK {src.name} -> {topic}/{dest.name}")


if __name__ == "__main__":
    main()

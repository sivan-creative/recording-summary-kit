"""Meeting / call summaries -> plain files, for people without monday.com.

Every summary becomes summaries_root/<topic>/<date> - <name>.md (readable in Google Drive, Word, any phone),
and every open task is added to summaries_root/משימות פתוחות.md as a checkbox line with a link to its summary.
Marking a task done = changing "- [ ]" to "- [x]" (or asking Claude to do it).

Input: the same JSON as push_to_monday.py (format in docs/summary-format.md).
Usage:
    python scripts/save_summary_files.py summaries.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_config, utf8_console


def main() -> None:
    utf8_console()
    cfg = load_config()
    root = Path(cfg["summaries_root"])
    tasks_file = root / "משימות פתוחות.md"
    root.mkdir(parents=True, exist_ok=True)
    if not tasks_file.exists():
        tasks_file.write_text("# משימות פתוחות\n\n", encoding="utf-8")

    for s in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")):
        folder = root / s.get("topic", "כללי")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{s['date']} - {s['name']}.md"
        if path.exists():
            print(f"skip (exists): {path.name}")
            continue
        lines = [f"# {s['name']}", "", f"**תאריך:** {s['date']}  ", f"**משתתפים:** {s.get('participants', '')}  ",
                 f"**מקור:** {s.get('source', 'הקלטה')}", "", s.get("purpose", ""), ""]
        if s.get("bullets"):
            lines += ["## עיקרי הדברים", ""] + [f"- {b}" for b in s["bullets"]] + [""]
        if s.get("decisions"):
            lines += ["## החלטות", "", s["decisions"], ""]
        if s.get("tasks"):
            lines += ["## משימות פתוחות", ""] + [f"- [ ] {t['name']} ({t.get('date', '')})" for t in s["tasks"]] + [""]
        if s.get("transcript"):
            lines += [f"[התמלול המלא](<{Path(s['transcript']).as_posix()}>)", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        rel = path.relative_to(root).as_posix()  # relative link, so it keeps working in Drive on any device
        with tasks_file.open("a", encoding="utf-8") as f:
            for t in s.get("tasks", []):
                f.write(f"- [ ] {t.get('date', '')} | {t['name']} | מתוך: [{s['name']}](<{rel}>)\n")
        print(f"OK {path}")


if __name__ == "__main__":
    main()

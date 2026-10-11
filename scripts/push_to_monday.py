"""Meeting / call summaries -> monday.com: an item in the summaries board (the summary itself as an update
on the item) + an item in the tasks board for every open task, linked back to the summary when a
connect-boards column is configured.

Input: a JSON file with a list of summaries (format in docs/summary-format.md).
Board and column IDs come from config.json -> "monday" (filled in during setup). Token: secrets_store.py
set MONDAY_API_TOKEN.

Usage:
    python scripts/push_to_monday.py summaries.json          # all
    python scripts/push_to_monday.py summaries.json <key>    # only one (to test)
A <file>.done.json is written next to the input; summaries already pushed are skipped on a re-run.
"""
import html
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import get_secret, load_config, utf8_console

CFG = load_config()
M = CFG.get("monday") or {}
TOKEN = None


def gql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.monday.com/v2",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={"Authorization": TOKEN, "API-Version": "2024-10", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        out = json.loads(r.read().decode("utf-8"))
    if out.get("errors") or out.get("error_message"):
        raise RuntimeError(json.dumps(out.get("errors") or out, ensure_ascii=False))
    return out["data"]


def create_item(board, group, name, cols) -> str:
    args = {"b": board, "n": name, "c": json.dumps(cols, ensure_ascii=False)}
    if group:
        args["g"] = group
        q = "mutation($b:ID!,$g:String!,$n:String!,$c:JSON!){create_item(board_id:$b,group_id:$g,item_name:$n,column_values:$c,create_labels_if_missing:true){id}}"
    else:
        q = "mutation($b:ID!,$n:String!,$c:JSON!){create_item(board_id:$b,item_name:$n,column_values:$c,create_labels_if_missing:true){id}}"
    return gql(q, args)["create_item"]["id"]


def body_html(s: dict) -> str:
    e = html.escape
    parts = [f"<h3>{e(s['name'])}</h3>", f"<p>{e(s.get('purpose', ''))}</p>"]
    if s.get("bullets"):
        parts.append("<p><b>עיקרי הדברים</b></p><ul>" + "".join(f"<li>{e(b)}</li>" for b in s["bullets"]) + "</ul>")
    if s.get("decisions"):
        parts.append(f"<p><b>החלטות:</b> {e(s['decisions'])}</p>")
    if s.get("tasks"):
        parts.append("<p><b>משימות פתוחות</b></p><ul>" +
                     "".join(f"<li>{e(t['name'])} ({e(t.get('date', ''))})</li>" for t in s["tasks"]) + "</ul>")
    parts.append(f"<p><i>מקור: {e(s.get('source', 'הקלטה'))}, תמלול אוטומטי מקומי. שמות ומספרים עלולים להיות לא מדויקים.</i></p>")
    return "".join(parts)


def push(s: dict) -> dict:
    cols_cfg = M.get("columns", {})
    cols = {}
    if cols_cfg.get("date") and s.get("date"):
        cols[cols_cfg["date"]] = {"date": s["date"]}
    if cols_cfg.get("participants") and s.get("participants"):
        cols[cols_cfg["participants"]] = s["participants"]
    if cols_cfg.get("decisions") and s.get("decisions"):
        cols[cols_cfg["decisions"]] = {"text": s["decisions"]}
    group = (M.get("group_by_topic") or {}).get(s.get("topic", ""), M.get("summaries_group"))
    item = create_item(M["summaries_board"], group, s["name"], cols)
    gql("mutation($i:ID!,$b:String!){create_update(item_id:$i,body:$b){id}}", {"i": item, "b": body_html(s)})

    task_ids = []
    if M.get("tasks_board"):
        tcfg = M.get("task_columns", {})
        for t in s.get("tasks", []):
            tcols = {}
            if tcfg.get("date") and t.get("date"):
                tcols[tcfg["date"]] = {"date": t["date"]}
            if tcfg.get("link_to_summary"):
                tcols[tcfg["link_to_summary"]] = {"item_ids": [int(item)]}
            task_ids.append(create_item(M["tasks_board"], M.get("tasks_group"), t["name"], tcols))
    return {"item": item, "tasks": task_ids}


def main() -> None:
    global TOKEN
    utf8_console()
    if not M.get("summaries_board"):
        raise SystemExit('config.json has no "monday" -> "summaries_board". Use save_summary_files.py instead.')
    TOKEN = get_secret("MONDAY_API_TOKEN")
    src = Path(sys.argv[1])
    only = sys.argv[2] if len(sys.argv) > 2 else None
    done_path = src.with_suffix(".done.json")
    done = json.loads(done_path.read_text(encoding="utf-8")) if done_path.exists() else {}
    for s in json.loads(src.read_text(encoding="utf-8")):
        if (only and s["key"] != only) or s["key"] in done:
            continue
        done[s["key"]] = push(s)
        done_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f'{s["key"]}: item {done[s["key"]]["item"]}, {len(done[s["key"]]["tasks"])} tasks', flush=True)


if __name__ == "__main__":
    main()

"""Create or update the Genie space from config/genie/space.yml (matched by title).

    python scripts/genie_space.py --dry-run                       # print the serialized space
    DATABRICKS_CONFIG_PROFILE=darts python scripts/genie_space.py  # create or update, prints the space id

The space id goes to the app as the genie-space resource (resources/app.yml).
"""

import argparse
import hashlib
import json
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "genie" / "space.yml"
FLAGS = {"entity_matching": "enable_entity_matching", "format_assistance": "enable_format_assistance", "exclude": "exclude"}


def _id(*parts: str) -> str:
    """Stable 32-hex id, so updating the space keeps the same ids."""
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def serialized_space(cfg: dict) -> dict:
    tables = []
    for t in cfg["tables"]:
        cols = []
        for name, c in sorted((t.get("columns") or {}).items()):
            entry = {"column_name": name}
            if c.get("description"):
                entry["description"] = [c["description"]]
            if c.get("synonyms"):
                entry["synonyms"] = list(c["synonyms"])
            entry |= {api: True for key, api in FLAGS.items() if c.get(key)}
            cols.append(entry)
        tables.append({"identifier": t["identifier"], **({"column_configs": cols} if cols else {})})
    table_notes = "\n".join(f"- {t['identifier'].split('.')[-1]}: {t['description']}" for t in cfg["tables"])
    instructions = cfg["instructions"].rstrip() + "\n## TABLES\n" + table_notes
    return {
        "version": 2,
        "config": {"sample_questions": sorted(({"id": _id("q", q), "question": [q]} for q in cfg["sample_questions"]),
                                              key=lambda x: x["id"])},
        "data_sources": {"tables": sorted(tables, key=lambda x: x["identifier"])},
        "instructions": {
            "text_instructions": [{"id": _id("text"), "content": [instructions]}],
            "example_question_sqls": sorted(({"id": _id("sql", e["question"]), "question": [e["question"]],
                                              "sql": [e["sql"].strip()]} for e in cfg["examples"]), key=lambda x: x["id"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--warehouse-id", default=None, help="default: the workspace's first SQL warehouse")
    args = parser.parse_args()
    cfg = yaml.safe_load(CONFIG.read_text())
    space = json.dumps(serialized_space(cfg))
    if args.dry_run:
        print(json.dumps(json.loads(space), indent=2))
        return

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    warehouse = args.warehouse_id or next(iter(w.warehouses.list())).id
    existing = next((s for s in (w.genie.list_spaces().spaces or []) if s.title == cfg["title"]), None)
    if existing:
        w.genie.update_space(existing.space_id, serialized_space=space, description=cfg["description"],
                             warehouse_id=warehouse)
        print(f"updated {existing.space_id}")
    else:
        created = w.genie.create_space(warehouse, space, title=cfg["title"], description=cfg["description"])
        print(f"created {created.space_id}")


if __name__ == "__main__":
    main()

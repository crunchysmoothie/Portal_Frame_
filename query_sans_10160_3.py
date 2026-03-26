import argparse
import json
from pathlib import Path


DATA_DIR = Path(".codes") / "sans_10160_3_parsed"


def load_json(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def safe_print(text: str):
    print(text.encode("cp1252", errors="replace").decode("cp1252", errors="replace"))


def query_clause(clause_no: str):
    pages = load_json("pages.json")
    needle = f"{clause_no} "
    for p in pages:
        lines = p["text"].splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith(needle):
                print(f"\n=== Clause {clause_no} on page {p['page']} ===")
                start = max(0, i - 2)
                end = min(len(lines), i + 40)
                safe_print("\n".join(lines[start:end]))
                return
    print(f"Clause {clause_no} not found.")


def query_table(table_no: int):
    pages = load_json("pages.json")
    needle = f"Table {table_no}"
    for p in pages:
        if needle.lower() in p["text"].lower():
            print(f"\n=== {needle} (page {p['page']}) ===")
            safe_print(p["text"])
            return
    print(f"{needle} not found.")


def query_keyword(keyword: str, limit: int):
    lines_path = DATA_DIR / "lines.jsonl"
    found = 0
    kw = keyword.lower()
    for raw in lines_path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(raw)
        if kw in rec["text"].lower():
            safe_print(f"p{rec['page']} l{rec['line']}: {rec['text']}")
            found += 1
            if found >= limit:
                break
    if found == 0:
        print("No matches found.")


def main():
    parser = argparse.ArgumentParser(description="Query parsed SANS 10160-3 dataset.")
    parser.add_argument("--clause", help="Clause number, e.g. 8.4.6")
    parser.add_argument("--table", type=int, help="Table number, e.g. 13")
    parser.add_argument("--keyword", help="Keyword search across all lines")
    parser.add_argument("--limit", type=int, default=30, help="Keyword result limit")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"Parsed data not found in {DATA_DIR}. Run parse_sans_10160_3.py first."
        )

    if args.clause:
        query_clause(args.clause)
    elif args.table is not None:
        query_table(args.table)
    elif args.keyword:
        query_keyword(args.keyword, args.limit)
    else:
        parser.error("Provide one of --clause, --table, or --keyword.")


if __name__ == "__main__":
    main()

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from pypdf import PdfReader


PDF_PATH = Path(".codes") / "SANS 10160-3.pdf"
OUT_DIR = Path(".codes") / "sans_10160_3_parsed"


CLAUSE_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)\s+(.+?)\s*$")
TABLE_RE = re.compile(r"\bTable\s+(\d+)\b", re.IGNORECASE)
FIG_RE = re.compile(r"\bFigure\s+(\d+)\b", re.IGNORECASE)


def normalize_text(text: str) -> str:
    # Keep unicode for fidelity, but normalize line endings and spacing.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def extract_pages(pdf_path: Path) -> List[Dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    pages = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(
            {
                "page": idx,
                "text": normalize_text(text),
            }
        )
    return pages


def index_clauses(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clauses: List[Dict[str, Any]] = []
    for p in pages:
        for line in p["text"].splitlines():
            match = CLAUSE_RE.match(line)
            if not match:
                continue
            clause_no, title = match.group(1), match.group(2)
            clauses.append(
                {
                    "clause": clause_no,
                    "title": title.strip(),
                    "page": p["page"],
                }
            )

    # Deduplicate same clause detected multiple times on headers/footers
    dedup = {}
    for c in clauses:
        key = c["clause"]
        if key not in dedup:
            dedup[key] = c
    return list(dedup.values())


def index_tables_and_figures(pages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    tables: Dict[str, Dict[str, Any]] = {}
    figures: Dict[str, Dict[str, Any]] = {}

    for p in pages:
        text = p["text"]
        lines = text.splitlines()

        for i, line in enumerate(lines):
            for m in TABLE_RE.finditer(line):
                num = m.group(1)
                if num not in tables:
                    # Use the line as title; if too short try next line.
                    title = line.strip()
                    if len(title) < 12 and i + 1 < len(lines):
                        title = f"{title} {lines[i + 1].strip()}".strip()
                    tables[num] = {
                        "table": int(num),
                        "title": title,
                        "page": p["page"],
                    }

            for m in FIG_RE.finditer(line):
                num = m.group(1)
                if num not in figures:
                    title = line.strip()
                    if len(title) < 12 and i + 1 < len(lines):
                        title = f"{title} {lines[i + 1].strip()}".strip()
                    figures[num] = {
                        "figure": int(num),
                        "title": title,
                        "page": p["page"],
                    }

    table_list = sorted(tables.values(), key=lambda x: x["table"])
    figure_list = sorted(figures.values(), key=lambda x: x["figure"])
    return {"tables": table_list, "figures": figure_list}


def build_search_lines(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in pages:
        for ln, line in enumerate(p["text"].splitlines(), start=1):
            s = line.strip()
            if not s:
                continue
            out.append({"page": p["page"], "line": ln, "text": s})
    return out


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = extract_pages(PDF_PATH)
    clauses = index_clauses(pages)
    refs = index_tables_and_figures(pages)
    lines = build_search_lines(pages)

    # 1) Full text (single file)
    full_text = []
    for p in pages:
        full_text.append(f"\n===== PAGE {p['page']} =====\n")
        full_text.append(p["text"])
    (OUT_DIR / "full_text.txt").write_text("\n".join(full_text), encoding="utf-8")

    # 2) Structured pages
    (OUT_DIR / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) Clause index
    (OUT_DIR / "clauses.json").write_text(json.dumps(clauses, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) Table/Figure index
    (OUT_DIR / "references.json").write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) Search-optimized line records
    (OUT_DIR / "lines.jsonl").write_text(
        "\n".join(json.dumps(rec, ensure_ascii=False) for rec in lines),
        encoding="utf-8",
    )

    manifest = {
        "source_pdf": str(PDF_PATH),
        "pages": len(pages),
        "clauses_indexed": len(clauses),
        "tables_indexed": len(refs["tables"]),
        "figures_indexed": len(refs["figures"]),
        "output_dir": str(OUT_DIR),
        "files": [
            "full_text.txt",
            "pages.json",
            "clauses.json",
            "references.json",
            "lines.jsonl",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

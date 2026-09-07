#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import pandas as pd


ID_PATTERN = re.compile(r"\bID\s*:\s*([A-Za-z0-9][A-Za-z0-9.\-]*)", re.IGNORECASE)
SPECIFY_ID_PATTERN = re.compile(r"<\s*specify\s+id\s*:?")
VERSION_PATTERN = re.compile(r"(?:^|[\s_\-])v(?:ersion)?\s*\d+(?:\.\d+)*$", re.IGNORECASE)


@dataclass
class Record:
    source: str
    guideline_name: str
    guideline_key: str
    record_id: str
    content: str


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_guideline_name(name: str) -> str:
    n = normalize_ws(name)
    n = re.sub(r"\.pdf$", "", n, flags=re.IGNORECASE)
    n = n.replace("_", " ")
    n = re.sub(r"[()\[\]{}]", " ", n)
    n = re.sub(r"\s+", " ", n).strip().lower()

    parts = [p for p in n.split(" ") if p]
    while parts and VERSION_PATTERN.search(parts[-1]):
        parts.pop()

    n = " ".join(parts)
    n = re.sub(r"\bversion\s*\d+(?:\.\d+)*\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\bv\s*\d+(?:\.\d+)*\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return normalize_ws(n)


def normalize_id(value: str) -> str:
    v = normalize_ws(value)
    v = re.sub(r"^id\s*:\s*", "", v, flags=re.IGNORECASE)
    v = re.sub(r"\(.*?version.*?\)", "", v, flags=re.IGNORECASE)
    v = re.sub(r"[^A-Za-z0-9.\-]", "", v)
    return v.upper()


def extract_id_from_text(text: str) -> str:
    m = ID_PATTERN.search(text)
    if not m:
        return ""
    return normalize_id(m.group(1))


def row_text(row: pd.Series) -> str:
    parts: list[str] = []
    for x in row.tolist():
        if pd.isna(x):
            continue
        t = normalize_ws(str(x))
        if not t:
            continue
        parts.append(t)
    return " | ".join(parts)


def score_content(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_ws(a).lower(), normalize_ws(b).lower()).ratio()


def pick_column(cols: list[str], explicit: str | None, candidates: Iterable[str]) -> str:
    if explicit:
        if explicit not in cols:
            raise ValueError(f"Column '{explicit}' not found. Available: {cols}")
        return explicit

    lowered = {c.lower(): c for c in cols}
    for candidate in candidates:
        c = lowered.get(candidate.lower())
        if c:
            return c

    for c in cols:
        lc = c.lower()
        if all(token in lc for token in ["guideline", "name"]):
            return c

    raise ValueError(f"Could not auto-detect column from candidates {list(candidates)} in {cols}")


def parse_pdf_records(csv_path: Path) -> list[Record]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if "pdf_name" not in df.columns:
        raise ValueError(f"Expected 'pdf_name' column in {csv_path}")

    records: list[Record] = []
    for pdf_name, group in df.groupby("pdf_name", sort=False):
        current_id = ""
        current_lines: list[str] = []

        def flush() -> None:
            nonlocal current_id, current_lines
            if not current_id:
                current_lines = []
                return
            content = normalize_ws(" \n ".join(current_lines))
            if content:
                records.append(
                    Record(
                        source="pdf",
                        guideline_name=str(pdf_name),
                        guideline_key=normalize_guideline_name(str(pdf_name)),
                        record_id=current_id,
                        content=content,
                    )
                )
            current_id = ""
            current_lines = []

        for _, row in group.iterrows():
            text = row_text(row)
            if not text:
                continue
            if "example" in text.lower():
                continue
            if SPECIFY_ID_PATTERN.search(text.lower()):
                continue

            found_id = extract_id_from_text(text)
            if found_id:
                flush()
                current_id = found_id
                current_lines = [text]
                continue

            if current_id:
                current_lines.append(text)

        flush()

    return records


def parse_xlsx_records(
    xlsx_path: Path,
    sheet_name: str | None,
    guideline_col: str | None,
    id_col: str | None,
) -> list[Record]:
    selected_sheet = 0 if sheet_name is None else sheet_name
    df = pd.read_excel(xlsx_path, sheet_name=selected_sheet, dtype=str)
    df = df.fillna("")
    columns = list(df.columns)

    g_col = pick_column(columns, guideline_col, ["Guideline Name", "guideline_name", "Guideline"])
    i_col = pick_column(columns, id_col, ["ID", "Id", "Control ID", "Requirement ID"])

    content_cols = [c for c in columns if c not in {g_col, i_col}]

    records: list[Record] = []
    for _, row in df.iterrows():
        guideline = normalize_ws(row[g_col])
        rec_id = normalize_id(str(row[i_col]))
        if not guideline or not rec_id:
            continue

        line_parts = []
        for c in content_cols:
            value = normalize_ws(row[c])
            if value:
                line_parts.append(f"{c}: {value}")

        records.append(
            Record(
                source="xlsx",
                guideline_name=guideline,
                guideline_key=normalize_guideline_name(guideline),
                record_id=rec_id,
                content=normalize_ws(" | ".join(line_parts)),
            )
        )

    return records


def write_outputs(
    out_dir: Path,
    matched_rows: list[dict],
    xlsx_only_rows: list[dict],
    pdf_only_rows: list[dict],
    mismatch_rows: list[dict],
    guideline_summary: list[dict],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(matched_rows).to_csv(out_dir / "matched_records.csv", index=False)
    pd.DataFrame(xlsx_only_rows).to_csv(out_dir / "xlsx_only.csv", index=False)
    pd.DataFrame(pdf_only_rows).to_csv(out_dir / "pdf_only.csv", index=False)
    pd.DataFrame(mismatch_rows).to_csv(out_dir / "content_mismatch.csv", index=False)
    pd.DataFrame(guideline_summary).to_csv(out_dir / "guideline_coverage.csv", index=False)


def compare_records(pdf_records: list[Record], xlsx_records: list[Record], mismatch_threshold: float) -> dict:
    pdf_by_key = {(r.guideline_key, r.record_id): r for r in pdf_records}
    xlsx_by_key = {(r.guideline_key, r.record_id): r for r in xlsx_records}

    matched_rows: list[dict] = []
    xlsx_only_rows: list[dict] = []
    pdf_only_rows: list[dict] = []
    mismatch_rows: list[dict] = []

    guideline_pdf = {}
    guideline_xlsx = {}
    for r in pdf_records:
        guideline_pdf.setdefault(r.guideline_key, set()).add(r.record_id)
    for r in xlsx_records:
        guideline_xlsx.setdefault(r.guideline_key, set()).add(r.record_id)

    for key in sorted(set(xlsx_by_key).intersection(pdf_by_key)):
        xr = xlsx_by_key[key]
        pr = pdf_by_key[key]
        sim = score_content(xr.content, pr.content)
        status = "exact" if sim >= 0.98 else "near" if sim >= mismatch_threshold else "mismatch"
        row = {
            "guideline_key": key[0],
            "record_id": key[1],
            "xlsx_guideline_name": xr.guideline_name,
            "pdf_guideline_name": pr.guideline_name,
            "similarity_score": round(sim, 4),
            "status": status,
            "xlsx_content": xr.content,
            "pdf_content": pr.content,
        }
        matched_rows.append(row)
        if status == "mismatch":
            mismatch_rows.append(row)

    for key in sorted(set(xlsx_by_key) - set(pdf_by_key)):
        xr = xlsx_by_key[key]
        xlsx_only_rows.append(
            {
                "guideline_key": xr.guideline_key,
                "record_id": xr.record_id,
                "xlsx_guideline_name": xr.guideline_name,
                "xlsx_content": xr.content,
            }
        )

    for key in sorted(set(pdf_by_key) - set(xlsx_by_key)):
        pr = pdf_by_key[key]
        pdf_only_rows.append(
            {
                "guideline_key": pr.guideline_key,
                "record_id": pr.record_id,
                "pdf_guideline_name": pr.guideline_name,
                "pdf_content": pr.content,
            }
        )

    all_guidelines = sorted(set(guideline_pdf) | set(guideline_xlsx))
    guideline_summary: list[dict] = []
    for g in all_guidelines:
        p_ids = guideline_pdf.get(g, set())
        x_ids = guideline_xlsx.get(g, set())
        guideline_summary.append(
            {
                "guideline_key": g,
                "pdf_id_count": len(p_ids),
                "xlsx_id_count": len(x_ids),
                "common_id_count": len(p_ids & x_ids),
                "pdf_only_id_count": len(p_ids - x_ids),
                "xlsx_only_id_count": len(x_ids - p_ids),
            }
        )

    return {
        "matched_rows": matched_rows,
        "xlsx_only_rows": xlsx_only_rows,
        "pdf_only_rows": pdf_only_rows,
        "mismatch_rows": mismatch_rows,
        "guideline_summary": guideline_summary,
    }


def discover_xlsx(path: Path) -> Path:
    matches = sorted(path.rglob("*.xlsx"))
    if not matches:
        raise FileNotFoundError(
            f"No .xlsx files found under {path}. Upload the file and pass --xlsx /absolute/path/to/file.xlsx"
        )
    if len(matches) > 1:
        raise FileNotFoundError(
            f"Multiple .xlsx files found under {path}; pass --xlsx explicitly. Candidates: {matches}"
        )
    return matches[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare guideline data from XLSX vs PDF-derived consolidated CSV")
    parser.add_argument(
        "--csv",
        default="/home/runner/work/cvcodebase/cvcodebase/gh-pages-site/assets/consolidated_id_tables.csv",
        help="Path to consolidated PDF CSV",
    )
    parser.add_argument(
        "--xlsx",
        default=None,
        help="Path to source XLSX file (optional if exactly one .xlsx exists under --discover-root)",
    )
    parser.add_argument(
        "--discover-root",
        default="/home/runner/work/cvcodebase/cvcodebase",
        help="Search root when --xlsx is omitted",
    )
    parser.add_argument("--sheet", default=None, help="XLSX sheet name (default: first sheet)")
    parser.add_argument("--guideline-col", default=None, help="Guideline-name column in XLSX")
    parser.add_argument("--id-col", default=None, help="ID column in XLSX")
    parser.add_argument(
        "--mismatch-threshold",
        type=float,
        default=0.75,
        help="Similarity threshold below which rows are flagged as content mismatch",
    )
    parser.add_argument(
        "--out-dir",
        default="/home/runner/work/cvcodebase/cvcodebase/gh-pages-site/assets/comparison_output",
        help="Output folder for comparison reports",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    if args.xlsx:
        xlsx_path = Path(args.xlsx).resolve()
    else:
        xlsx_path = discover_xlsx(Path(args.discover_root).resolve())

    if not xlsx_path.exists():
        raise FileNotFoundError(f"XLSX not found: {xlsx_path}")

    pdf_records = parse_pdf_records(csv_path)
    xlsx_records = parse_xlsx_records(
        xlsx_path=xlsx_path,
        sheet_name=args.sheet,
        guideline_col=args.guideline_col,
        id_col=args.id_col,
    )

    result = compare_records(
        pdf_records=pdf_records,
        xlsx_records=xlsx_records,
        mismatch_threshold=args.mismatch_threshold,
    )

    out_dir = Path(args.out_dir).resolve()
    write_outputs(
        out_dir=out_dir,
        matched_rows=result["matched_rows"],
        xlsx_only_rows=result["xlsx_only_rows"],
        pdf_only_rows=result["pdf_only_rows"],
        mismatch_rows=result["mismatch_rows"],
        guideline_summary=result["guideline_summary"],
    )

    print(f"XLSX: {xlsx_path}")
    print(f"PDF CSV: {csv_path}")
    print(f"Output dir: {out_dir}")
    print(f"PDF records: {len(pdf_records)}")
    print(f"XLSX records: {len(xlsx_records)}")
    print(f"Matched records: {len(result['matched_rows'])}")
    print(f"XLSX only: {len(result['xlsx_only_rows'])}")
    print(f"PDF only: {len(result['pdf_only_rows'])}")
    print(f"Content mismatches: {len(result['mismatch_rows'])}")


if __name__ == "__main__":
    main()

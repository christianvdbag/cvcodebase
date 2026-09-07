#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import pandas as pd
from docx import Document
from openpyxl.styles import PatternFill


SECTION_ID_PATTERN = re.compile(r"^ID\s*:\s*([A-Za-z0-9][A-Za-z0-9.\-]*)", re.IGNORECASE)
ROW_ID_PATTERN = re.compile(r"^\s*([A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*)\b")
VERSION_PATTERN = re.compile(r"(?:^|[\s_\-])v(?:ersion)?\s*\d+(?:\.\d+)*$", re.IGNORECASE)
REMOVE_AFTER_MARKERS = (
    "asset-types:",
    "asset type:",
    "key references:",
    "key reference:",
    "regulatory standards:",
)


@dataclass
class Record:
    source: str
    guideline_name: str
    guideline_key: str
    record_id: str
    control_description: str
    control_requirement: str


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_for_compare(text: str) -> str:
    t = normalize_ws(text).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def normalize_guideline_name(name: str) -> str:
    n = normalize_ws(name)
    n = re.sub(r"\.(pdf|docx)$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"_final$", "", n, flags=re.IGNORECASE)
    n = n.replace("_", " ")
    n = re.sub(r"[()\[\]{}]", " ", n)
    n = re.sub(r"\s+", " ", n).strip().lower()
    parts = [p for p in n.split(" ") if p]
    while parts and VERSION_PATTERN.search(parts[-1]):
        parts.pop()
    n = " ".join(parts)
    n = re.sub(r"\bversion\s*\d+(?:\.\d+)*\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\bv\s*\.?\s*\d+(?:\.\d+)*\b", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\bguideline\b", "", n, flags=re.IGNORECASE)
    n = n.replace("idp", "individual data processing")
    n = n.replace("nclc", "no low code")
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return normalize_ws(n)


def normalize_id(value: str) -> str:
    v = normalize_ws(value)
    v = re.sub(r"^id\s*:\s*", "", v, flags=re.IGNORECASE)
    v = re.sub(r"\(.*?version.*?\)", "", v, flags=re.IGNORECASE)
    v = re.sub(r"[^A-Za-z0-9.\-]", "", v)
    return v.upper()


def strip_after_markers(text: str) -> str:
    t = normalize_ws(text)
    lower = t.lower()
    cut = len(t)
    for marker in REMOVE_AFTER_MARKERS:
        idx = lower.find(marker)
        if idx >= 0:
            cut = min(cut, idx)
    return normalize_ws(t[:cut])


def clean_requirement_text(text: str) -> str:
    t = normalize_ws(text)
    t = t.replace("  ", " ")
    t = t.replace(" and key Hardware,", " and key management technology changes.")
    t = strip_after_markers(t)
    return normalize_ws(t)


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
    raise ValueError(f"Could not auto-detect column from candidates {list(candidates)} in {cols}")


def discover_docx(path: Path) -> list[Path]:
    return sorted(p for p in path.glob("*.docx") if "risk ai guideline" not in p.name.lower())


def parse_docx_records(docx_paths: list[Path]) -> list[Record]:
    records: list[Record] = []
    for docx_path in docx_paths:
        guideline_name = re.sub(r"_final$", "", docx_path.stem, flags=re.IGNORECASE)
        guideline_key = normalize_guideline_name(guideline_name)
        doc = Document(docx_path)

        for table in doc.tables:
            if not table.rows or len(table.columns) < 2:
                continue
            first_row = [normalize_ws(c.text) for c in table.rows[0].cells]
            if len(first_row) < 2:
                continue
            if "<specify id" in first_row[0].lower():
                continue
            section_match = SECTION_ID_PATTERN.search(first_row[0])
            if not section_match:
                continue
            section_description = normalize_ws(first_row[1])
            previous_record: Record | None = None

            for row in table.rows[1:]:
                cells = [normalize_ws(c.text) for c in row.cells]
                if len(cells) < 2:
                    continue
                left = cells[0]
                right = cells[1]
                if not left and not right:
                    continue
                if "<" in left.lower() and "specify" in left.lower():
                    continue
                id_match = ROW_ID_PATTERN.match(left)

                if id_match:
                    record_id = normalize_id(id_match.group(1))
                    requirement = clean_requirement_text(right)
                    if not record_id:
                        continue
                    rec = Record(
                        source="docx",
                        guideline_name=guideline_name,
                        guideline_key=guideline_key,
                        record_id=record_id,
                        control_description=section_description,
                        control_requirement=requirement,
                    )
                    records.append(rec)
                    previous_record = rec
                elif previous_record:
                    continuation = clean_requirement_text(" ".join([left, right]).strip())
                    if continuation:
                        previous_record.control_requirement = normalize_ws(
                            f"{previous_record.control_requirement} {continuation}"
                        )
    return records


def parse_xlsm_records(
    xlsm_path: Path,
    sheet_name: str,
    header_row: int,
    guideline_col: str,
    id_col: str,
    description_col: str,
    requirement_col: str,
    deleted_col: str,
) -> list[Record]:
    df = pd.read_excel(xlsm_path, sheet_name=sheet_name, header=header_row, dtype=str).fillna("")
    cols = [str(c) for c in df.columns]
    g_col = pick_column(cols, guideline_col, ["Name of Guideline", "Guideline Name"])
    i_col = pick_column(cols, id_col, ["MCF ID", "ID", "Control ID"])
    d_col = pick_column(cols, description_col, ["Control description"])
    r_col = pick_column(cols, requirement_col, ["Control requirements v8.0", "Control Requirement"])
    del_col = pick_column(cols, deleted_col, ["Deleted"])

    df = df[df[del_col].astype(str).str.strip().str.lower() == "no"]
    df = df[~df[g_col].astype(str).str.lower().str.contains("risk ai", na=False)]

    records: list[Record] = []
    for _, row in df.iterrows():
        guideline = normalize_ws(row[g_col])
        record_id = normalize_id(str(row[i_col]))
        if not guideline or not record_id:
            continue
        records.append(
            Record(
                source="xlsm",
                guideline_name=guideline,
                guideline_key=normalize_guideline_name(guideline),
                record_id=record_id,
                control_description=normalize_ws(row[d_col]),
                control_requirement=normalize_ws(row[r_col]),
            )
        )
    return records


def dedupe_records(records: list[Record]) -> dict[tuple[str, str], Record]:
    result: dict[tuple[str, str], Record] = {}
    for r in records:
        key = (r.guideline_key, r.record_id)
        existing = result.get(key)
        if existing is None:
            result[key] = r
            continue
        new_len = len(r.control_requirement) + len(r.control_description)
        old_len = len(existing.control_requirement) + len(existing.control_description)
        if new_len > old_len:
            result[key] = r
        elif not existing.control_description and r.control_description:
            existing.control_description = r.control_description
    return result


def score_text(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_ws(a).lower(), normalize_ws(b).lower()).ratio()


def build_status(docx_row: Record | None, xlsm_row: Record | None) -> str:
    if docx_row is None:
        return "Missing in DOCX"
    if xlsm_row is None:
        return "Missing in XLSM"
    desc_diff = normalize_for_compare(docx_row.control_description) != normalize_for_compare(xlsm_row.control_description)
    req_diff = normalize_for_compare(docx_row.control_requirement) != normalize_for_compare(xlsm_row.control_requirement)
    if desc_diff and req_diff:
        return "Content delta: description and requirement differ"
    if desc_diff:
        return "Content delta: description differs"
    if req_diff:
        return "Content delta: requirement differs"
    return "Match"


def compare_records(docx_records: list[Record], xlsm_records: list[Record]) -> list[dict]:
    docx_by_key = dedupe_records(docx_records)
    xlsm_by_key = dedupe_records(xlsm_records)
    rows: list[dict] = []
    matched_docx_keys: set[tuple[str, str]] = set()
    matched_xlsm_keys: set[tuple[str, str]] = set()

    common_keys = sorted(set(docx_by_key) & set(xlsm_by_key))
    for key in common_keys:
        d = docx_by_key[key]
        x = xlsm_by_key[key]
        matched_docx_keys.add(key)
        matched_xlsm_keys.add(key)
        rows.append(
            {
                "Status": build_status(d, x),
                "Guideline": (d.guideline_name if d else x.guideline_name),
                "ID": d.record_id,
                "XLSM ID": x.record_id,
                "DOCX Control Description": d.control_description if d else "",
                "DOCX Control Requirement": d.control_requirement if d else "",
                "XLSM Control Description": x.control_description if x else "",
                "XLSM Control Requirement": x.control_requirement if x else "",
            }
        )

    docx_by_guideline: dict[str, list[Record]] = {}
    xlsm_by_guideline: dict[str, list[Record]] = {}
    for key, r in docx_by_key.items():
        if key in matched_docx_keys:
            continue
        docx_by_guideline.setdefault(r.guideline_key, []).append(r)
    for key, r in xlsm_by_key.items():
        if key in matched_xlsm_keys:
            continue
        xlsm_by_guideline.setdefault(r.guideline_key, []).append(r)

    guidelines = sorted(set(docx_by_guideline) | set(xlsm_by_guideline))
    for guideline_key in guidelines:
        d_left = docx_by_guideline.get(guideline_key, [])
        x_left = xlsm_by_guideline.get(guideline_key, [])
        score_candidates: list[tuple[float, int, int]] = []
        for i, d in enumerate(d_left):
            for j, x in enumerate(x_left):
                req_score = score_text(d.control_requirement, x.control_requirement)
                desc_score = score_text(d.control_description, x.control_description)
                score = req_score * 0.85 + desc_score * 0.15
                if score >= 0.52:
                    score_candidates.append((score, i, j))
        score_candidates.sort(reverse=True)

        used_d: set[int] = set()
        used_x: set[int] = set()
        for score, i, j in score_candidates:
            if i in used_d or j in used_x:
                continue
            used_d.add(i)
            used_x.add(j)
            d = d_left[i]
            x = x_left[j]
            status = build_status(d, x)
            if d.record_id != x.record_id:
                status = f"{status} (fuzzy id-map)"
            rows.append(
                {
                    "Status": status,
                    "Guideline": d.guideline_name,
                    "ID": d.record_id,
                    "XLSM ID": x.record_id,
                    "DOCX Control Description": d.control_description,
                    "DOCX Control Requirement": d.control_requirement,
                    "XLSM Control Description": x.control_description,
                    "XLSM Control Requirement": x.control_requirement,
                }
            )

        for i, d in enumerate(d_left):
            if i in used_d:
                continue
            rows.append(
                {
                    "Status": "Missing in XLSM",
                    "Guideline": d.guideline_name,
                    "ID": d.record_id,
                    "XLSM ID": "",
                    "DOCX Control Description": d.control_description,
                    "DOCX Control Requirement": d.control_requirement,
                    "XLSM Control Description": "",
                    "XLSM Control Requirement": "",
                }
            )
        for j, x in enumerate(x_left):
            if j in used_x:
                continue
            rows.append(
                {
                    "Status": "Missing in DOCX",
                    "Guideline": x.guideline_name,
                    "ID": "",
                    "XLSM ID": x.record_id,
                    "DOCX Control Description": "",
                    "DOCX Control Requirement": "",
                    "XLSM Control Description": x.control_description,
                    "XLSM Control Requirement": x.control_requirement,
                }
            )

    rows.sort(key=lambda r: (r["Guideline"], str(r["ID"] or r["XLSM ID"])))
    return rows


def write_outputs(out_xlsx: Path, out_docx_csv: Path, comparison_rows: list[dict], docx_records: list[Record]) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    out_docx_csv.parent.mkdir(parents=True, exist_ok=True)

    docx_df = pd.DataFrame(
        [
            {
                "docx_name": r.guideline_name,
                "guideline_key": r.guideline_key,
                "id": r.record_id,
                "control_description": r.control_description,
                "control_requirement": r.control_requirement,
            }
            for r in docx_records
        ]
    )
    docx_df.to_csv(out_docx_csv, index=False)

    comp_df = pd.DataFrame(comparison_rows)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        comp_df.to_excel(writer, sheet_name="id_detail_delta", index=False)

        ws = writer.book["id_detail_delta"]
        highlight = PatternFill(start_color="FFF4B084", end_color="FFF4B084", fill_type="solid")
        for row_idx, row in enumerate(comparison_rows, start=2):
            status = row["Status"]
            if status.startswith("Missing in DOCX"):
                ws.cell(row=row_idx, column=1).fill = highlight
                ws.cell(row=row_idx, column=5).fill = highlight
                ws.cell(row=row_idx, column=6).fill = highlight
            elif status.startswith("Missing in XLSM"):
                ws.cell(row=row_idx, column=1).fill = highlight
                ws.cell(row=row_idx, column=7).fill = highlight
                ws.cell(row=row_idx, column=8).fill = highlight
            elif "description and requirement differ" in status:
                ws.cell(row=row_idx, column=1).fill = highlight
                ws.cell(row=row_idx, column=5).fill = highlight
                ws.cell(row=row_idx, column=6).fill = highlight
                ws.cell(row=row_idx, column=7).fill = highlight
                ws.cell(row=row_idx, column=8).fill = highlight
            elif "description differs" in status:
                ws.cell(row=row_idx, column=1).fill = highlight
                ws.cell(row=row_idx, column=5).fill = highlight
                ws.cell(row=row_idx, column=7).fill = highlight
            elif "requirement differs" in status:
                ws.cell(row=row_idx, column=1).fill = highlight
                ws.cell(row=row_idx, column=6).fill = highlight
                ws.cell(row=row_idx, column=8).fill = highlight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare guideline data from DOCX tables vs XLSM source")
    parser.add_argument(
        "--docx-dir",
        default="/home/runner/work/cvcodebase/cvcodebase/gh-pages-site/assets",
        help="Folder containing guideline .docx files",
    )
    parser.add_argument(
        "--xlsm",
        default="/home/runner/work/cvcodebase/cvcodebase/gh-pages-site/assets/ICTR-CF_v7.1_2026-08-21_final_published_unprotected_BASIS for 8.0.xlsm",
        help="Path to source XLSM",
    )
    parser.add_argument("--sheet", default="Mapped - v8 for UPDATE", help="XLSM sheet name")
    parser.add_argument("--header-row", type=int, default=7, help="0-based header row index in XLSM")
    parser.add_argument("--guideline-col", default="Name of Guideline", help="Guideline column")
    parser.add_argument("--id-col", default="MCF ID", help="ID column")
    parser.add_argument("--description-col", default="Control description", help="Control description column")
    parser.add_argument("--requirement-col", default="Control requirements v8.0", help="Control requirement column")
    parser.add_argument("--deleted-col", default="Deleted", help="Deleted marker column")
    parser.add_argument(
        "--out-xlsx",
        default="/home/runner/work/cvcodebase/cvcodebase/gh-pages-site/assets/id_detail_level_delta_excl_risk_ai.xlsx",
        help="Output XLSX with deltas",
    )
    parser.add_argument(
        "--out-docx-csv",
        default="/home/runner/work/cvcodebase/cvcodebase/gh-pages-site/assets/consolidated_docx_id_tables.csv",
        help="Output CSV with parsed DOCX records",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    docx_dir = Path(args.docx_dir).resolve()
    xlsm_path = Path(args.xlsm).resolve()
    out_xlsx = Path(args.out_xlsx).resolve()
    out_docx_csv = Path(args.out_docx_csv).resolve()

    if not docx_dir.exists():
        raise FileNotFoundError(f"DOCX dir not found: {docx_dir}")
    if not xlsm_path.exists():
        raise FileNotFoundError(f"XLSM not found: {xlsm_path}")

    docx_paths = discover_docx(docx_dir)
    if not docx_paths:
        raise FileNotFoundError(f"No DOCX files found in {docx_dir}")

    docx_records = parse_docx_records(docx_paths)
    xlsm_records = parse_xlsm_records(
        xlsm_path=xlsm_path,
        sheet_name=args.sheet,
        header_row=args.header_row,
        guideline_col=args.guideline_col,
        id_col=args.id_col,
        description_col=args.description_col,
        requirement_col=args.requirement_col,
        deleted_col=args.deleted_col,
    )
    comparison_rows = compare_records(docx_records, xlsm_records)
    write_outputs(out_xlsx, out_docx_csv, comparison_rows, docx_records)

    status_counts = pd.DataFrame(comparison_rows)["Status"].value_counts()
    print(f"DOCX parsed records: {len(docx_records)}")
    print(f"XLSM parsed records: {len(xlsm_records)}")
    print(status_counts.to_string())
    print(f"Wrote DOCX CSV: {out_docx_csv}")
    print(f"Wrote comparison XLSX: {out_xlsx}")


if __name__ == "__main__":
    main()

import re
from datetime import datetime
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("data-cleaner")

# ---------- field-level cleaners ----------

def normalize_date(raw):
    if raw is None or str(raw).strip().lower() in ("", "n/a", "none", "null", "nan"):
        return None, "missing_date"
    if isinstance(raw, datetime):
        return raw.date().isoformat(), None
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(str(raw).strip(), fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, f"unparseable_date:{raw}"

def normalize_number(raw):
    if raw is None or str(raw).strip() == "":
        return None, "missing_value"
    cleaned = re.sub(r"[^\d.\-]", "", str(raw))
    if cleaned in ("", "-", "."):
        return None, f"unparseable_number:{raw}"
    try:
        val = float(cleaned)
    except ValueError:
        return None, f"unparseable_number:{raw}"
    if val < 0:
        return val, f"negative_value:{val}"   # keep value, but flag for review
    return val, None

def normalize_quantity_with_unit(raw):
    """Handles values like '5360 HA', '1178.88', '4' -> (number, unit)."""
    if raw is None or str(raw).strip() == "":
        return {"value": None, "unit": None}, "missing_value"
    match = re.match(r"^\s*([\d.]+)\s*([A-Za-z]*)\s*$", str(raw))
    if not match:
        return {"value": None, "unit": None}, f"unparseable_quantity:{raw}"
    val, unit = match.groups()
    return {"value": float(val), "unit": unit or None}, None

def normalize_category(raw, mapping, canonical_set=None):
    """Generic categorical cleaner: strips, lowercases for lookup, maps typos/variants."""
    if raw is None or str(raw).strip() == "":
        return "Unknown", "missing_category"
    key = re.sub(r"\s+", " ", str(raw).strip().lower())
    resolved = mapping.get(key, str(raw).strip())
    if canonical_set and resolved not in canonical_set:
        return resolved, f"unmapped_category:{raw}"
    return resolved, None

def split_multi_value(raw, sep="+"):
    """'Dock + DMO + Spectra' -> ['Dock', 'DMO', 'Spectra']"""
    if raw is None or str(raw).strip() == "":
        return [], "missing_value"
    return [p.strip() for p in str(raw).split(sep) if p.strip()], None

def parse_deal_stage(raw):
    """'B. Sales Qualified Leads' -> {'order': 2, 'label': 'Sales Qualified Leads'}"""
    if raw is None or str(raw).strip() == "":
        return {"order": None, "label": None}, "missing_stage"
    match = re.match(r"^\s*([A-Z])\.\s*(.+)$", str(raw))
    if not match:
        return {"order": None, "label": str(raw).strip()}, f"unparseable_stage:{raw}"
    letter, label = match.groups()
    return {"order": ord(letter.upper()) - ord("A") + 1, "label": label.strip()}, None

def validate_code(raw, pattern):
    if raw is None or str(raw).strip() == "":
        return None, "missing_code"
    if not re.match(pattern, str(raw).strip()):
        return str(raw).strip(), f"invalid_code_format:{raw}"
    return str(raw).strip(), None

# ---------- canonical mappings (extend as you see more variants) ----------

STATUS_MAP = {
    "billed": "Billed", "bille d": "Billed", "billed ": "Billed",
    "fully billed": "Fully Billed", "partially billed": "Partially Billed",
    "not billed yet": "Not Billed Yet", "stuck": "Stuck",
    "update required": "Update Required", "not billable": "Not Billable",
}
CLOSURE_PROB_SET = {"High", "Medium", "Low"}

CLEANERS = {
    "date": normalize_date,
    "number": normalize_number,
    "quantity_unit": normalize_quantity_with_unit,
    "multi_value": split_multi_value,
    "deal_stage": parse_deal_stage,
}

# ---------- row-level junk detection ----------

def is_header_leak_row(record: dict, columns: list[str]) -> bool:
    """Flags rows where a cell's value literally equals its own column name —
    a copy-paste artifact from stacked CSV exports."""
    return any(str(record.get(c, "")).strip() == c for c in columns)

def dedupe(records: list[dict]) -> tuple[list[dict], int]:
    seen, out = set(), []
    for r in records:
        key = tuple(sorted((k, str(v)) for k, v in r.items()))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out, len(records) - len(out)

# ---------- main tool ----------

@mcp.tool()
def clean_board_data(records: list[dict], field_types: dict[str, str]) -> dict:
    """
    Cleans raw monday.com board records.
    field_types maps field name -> cleaner type:
      "date" | "number" | "quantity_unit" | "multi_value" | "deal_stage"
      or a categorical mapping name: "status" (uses STATUS_MAP), "closure_probability"
    Drops header-leak rows and exact duplicates before cleaning.
    Returns cleaned records plus a structured data-quality report.
    """
    columns = list(field_types.keys())
    issues = []

    # 1. strip junk rows
    junk_idx = [i for i, r in enumerate(records) if is_header_leak_row(r, columns)]
    records = [r for i, r in enumerate(records) if i not in junk_idx]
    if junk_idx:
        issues.append({"type": "header_leak_rows_removed", "count": len(junk_idx), "rows": junk_idx})

    # 2. dedupe
    records, dupe_count = dedupe(records)
    if dupe_count:
        issues.append({"type": "exact_duplicates_removed", "count": dupe_count})

    # 3. field-level cleaning
    cleaned = []
    for i, rec in enumerate(records):
        out = dict(rec)
        for field, ftype in field_types.items():
            raw = rec.get(field)
            if ftype == "status":
                val, issue = normalize_category(raw, STATUS_MAP)
            elif ftype == "closure_probability":
                val, issue = normalize_category(raw, {}, canonical_set=CLOSURE_PROB_SET)
            else:
                cleaner = CLEANERS.get(ftype)
                if not cleaner:
                    continue
                val, issue = cleaner(raw)
            out[field] = val
            if issue:
                issues.append({"row": i, "field": field, "issue": issue})
        cleaned.append(out)

    return {
        "records": cleaned,
        "quality_report": {
            "total_rows_after_cleanup": len(cleaned),
            "rows_with_field_issues": len({i["row"] for i in issues if "row" in i}),
            "issues": issues,
        },
    }

if __name__ == "__main__":
    mcp.run()
"""Parsing + validation for organizer-provided Google Form Excel/CSV registration exports.

The exact spreadsheet column names are NOT hardcoded. Headers are normalized and
matched against a configurable alias table so a typical Google Form export
("Team Name", "Leader Email ID", "Member 1", ...) is detected automatically.
"""
import csv
import io
import json
import re
import secrets
import string
from typing import Any, Dict, List

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# --- canonical field -> accepted header aliases (normalized: lower, alnum only) ---
_HEADER_ALIASES: Dict[str, List[str]] = {
    "team_name": [
        "teamname", "teamname", "team", "nameofteam", "teamnameatheteam",
        "whatisthenameofyourteam", "teamnameyourtaketeam",
    ],
    "leader_name": [
        "leadername", "teamleader", "nameofleader", "teammemberleader",
        "leader", "teamleadername", "nameofteamleader", "leaderfullname",
        "whatisthenameoftheteamleader", "teamleadernameth",
    ],
    "leader_email": [
        "leaderemail", "teamleaderemail", "emailofleader", "leaderemailid",
        "emailid", "email", "leaderemailaddress", "emailidofteamleader",
        "whatistheemailidofyourteamleader", "teammembersemail",
    ],
}

_MEMBER_NAME_PATTERN = re.compile(r"^(?:member|teammate|participant)\s*(\d+)(?:\s*(?:name|fullname))?$")
_MEMBER_EMAIL_PATTERN = re.compile(r"^(?:member|teammate|participant)\s*(\d+)(?:\s*(?:email|emailid))$")

MAX_MEMBER_COLUMNS = 8

def _norm_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())

def _detect_columns(headers: List[str]) -> Dict[str, Any]:
    """Map spreadsheet headers to canonical fields.

    Returns {"team_name": col_idx, "leader_name": idx, "leader_email": idx,
             "member_names": {1: idx, ...}, "member_emails": {1: idx, ...}}
    and an "errors" list for anything unresolved.
    """
    mapping: Dict[str, Any] = {
        "col_to_family": {},
        "member_names": {},
        "member_emails": {},
        "team_name": None,
        "leader_name": None,
        "leader_email": None,
    }
    normalized = [_norm_header(h) for h in headers]
    used_families: Dict[str, int] = {}

    for idx, norm in enumerate(normalized):
        if not norm:
            continue
        matched = False
        for family, aliases in _HEADER_ALIASES.items():
            if norm in aliases:
                mapping[family] = idx
                mapping["col_to_family"][idx] = family
                used_families[family] = idx
                matched = True
                break
        if matched:
            continue

        m = _MEMBER_NAME_PATTERN.match(norm)
        if m:
            number = int(m.group(1))
            if 1 <= number <= MAX_MEMBER_COLUMNS:
                if number not in mapping["member_names"]:
                    mapping["member_names"][number] = idx
                    mapping["col_to_family"][idx] = f"member_name:{number}"
                matched = True
                continue

        m = _MEMBER_EMAIL_PATTERN.match(norm)
        if m:
            number = int(m.group(1))
            if 1 <= number <= MAX_MEMBER_COLUMNS:
                if number not in mapping["member_emails"]:
                    mapping["member_emails"][number] = idx
                    mapping["col_to_family"][idx] = f"member_email:{number}"
                matched = True
                continue

    errors = []
    if mapping["team_name"] is None:
        errors.append("Could not detect a 'Team Name' column.")
    if mapping["leader_name"] is None:
        errors.append("Could not detect a 'Leader Name' column.")
    if mapping["leader_email"] is None:
        errors.append("Could not detect a 'Leader Email' column.")
    return mapping, errors

def _is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))

def _default_password() -> str:
    """Return a one-time password with mixed character classes.

    The plaintext value is returned to the administrator once; callers persist
    only its password hash.
    """
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    password = required + [secrets.choice(alphabet) for _ in range(10)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)

def parse_registration_file(filename: str, content: bytes, simple_mode: bool = False) -> Dict[str, Any]:
    """Parse an uploaded .xlsx / .csv into normalized rows.

    Returns:
      {
        "rows": [{"row_number", "team_name", "leader_name", "leader_email",
                  "members": [{"name","email"}], "warnings": [...]}],
        "warnings": [...],
        "errors": [...],
        "detected_columns": {...},
      }
    """
    lower_name = filename.lower()
    try:
        if lower_name.endswith(".xlsx") or lower_name.endswith(".xlsm"):
            data = _read_xlsx(content)
        elif lower_name.endswith(".csv"):
            data = _read_csv(content)
        else:
            return {"rows": [], "warnings": [], "errors": ["Unsupported file type. Upload .xlsx or .csv."], "detected_columns": {}}
    except Exception as exc:  # pragma: no cover - defensive
        return {"rows": [], "warnings": [], "errors": [f"Could not read file: {exc}"], "detected_columns": {}}

    if not data:
        return {"rows": [], "warnings": [], "errors": ["The file contains no rows."], "detected_columns": {}}

    headers = data[0]
    mapping, header_errors = _detect_columns(headers)
    errors = list(header_errors)
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    if mapping["team_name"] is None or mapping["leader_name"] is None or mapping["leader_email"] is None:
        return {"rows": [], "warnings": warnings, "errors": errors, "detected_columns": mapping}

    seen_teams: Dict[str, int] = {}
    seen_leader_emails: Dict[str, int] = {}

    for row_idx, raw_row in enumerate(data[1:], start=2):
        if raw_row is None:
            continue
        cells = [str(c).strip() if c is not None else "" for c in raw_row]
        if not any(cells):
            continue

        def cell(family: str) -> str:
            idx = mapping.get(family)
            return cells[idx] if idx is not None and idx < len(cells) else ""

        team_name = cell("team_name")
        leader_name = cell("leader_name")
        leader_email = cell("leader_email")
        row_warnings: List[str] = []

        if not team_name or not leader_name or not leader_email:
            missing = ", ".join(
                name for name, value in [
                    ("team name", team_name), ("leader name", leader_name), ("leader email", leader_email)
                ] if not value
            )
            errors.append(f"Row {row_idx}: missing required field(s): {missing}.")
            continue

        if not _is_valid_email(leader_email):
            errors.append(f"Row {row_idx}: leader email '{leader_email}' is not a valid email.")
            continue

        # duplicate detection within the sheet
        prev_team_row = seen_teams.get(team_name.lower())
        if prev_team_row is not None:
            warnings.append(f"Row {row_idx}: team '{team_name}' already appears at row {prev_team_row}.")
        else:
            seen_teams[team_name.lower()] = row_idx

        prev_leader_row = seen_leader_emails.get(leader_email.lower())
        if prev_leader_row is not None:
            warnings.append(f"Row {row_idx}: leader email '{leader_email}' already appears at row {prev_leader_row}.")
        else:
            seen_leader_emails[leader_email.lower()] = row_idx

        members: List[Dict[str, str]] = []
        for number in sorted(set(list(mapping["member_names"].keys()) + list(mapping["member_emails"].keys()))):
            name_idx = mapping["member_names"].get(number)
            email_idx = mapping["member_emails"].get(number)
            member_name = cells[name_idx] if name_idx is not None and name_idx < len(cells) else ""
            member_email = cells[email_idx] if email_idx is not None and email_idx < len(cells) else ""
            if not member_name and not member_email:
                continue
            if member_email and not _is_valid_email(member_email):
                warnings.append(f"Row {row_idx}: member {number} email '{member_email}' is malformed and will be ignored.")
                member_email = ""
            members.append({"name": member_name, "email": member_email})

        rows.append({
            "row_number": row_idx,
            "team_name": team_name,
            "leader_name": leader_name,
            "leader_email": leader_email,
            "members": members,
            "warnings": row_warnings,
            "status": "new",
        })

    return {
        "rows": rows,
        "warnings": warnings,
        "errors": errors,
        "detected_columns": mapping,
    }

def _read_csv(content: bytes) -> List[List[str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader]

def _read_xlsx(content: bytes) -> List[List[str]]:
    from openpyxl import load_workbook
    from io import BytesIO
    wb = load_workbook(BytesIO(content), data_only=True, read_only=True)
    sheet = wb.active
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(list(row))
    wb.close()
    return rows

def generate_credentials(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Produce one credential per leader account from parsed rows (passwords NOT persisted)."""
    credentials = []
    for row in rows:
        password = _default_password()
        credentials.append({
            "team_name": row["team_name"],
            "name": row["leader_name"],
            "email": row["leader_email"],
            "username": row["leader_email"],
            "temporary_password": password,
            "role": "leader",
        })
    return credentials

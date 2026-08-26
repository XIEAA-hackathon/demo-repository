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
            if number >= 1:
                if number not in mapping["member_names"]:
                    mapping["member_names"][number] = idx
                    mapping["col_to_family"][idx] = f"member_name:{number}"
                matched = True
                continue

        m = _MEMBER_EMAIL_PATTERN.match(norm)
        if m:
            number = int(m.group(1))
            if number >= 1:
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
    """Parse and validate an uploaded registration workbook without mutating data."""
    lower_name = filename.lower()
    empty_result = {"rows": [], "warnings": [], "errors": [], "row_errors": [], "detected_columns": {}, "source_headers": []}
    try:
        if lower_name.endswith((".xlsx", ".xlsm")):
            data = _read_xlsx(content)
        elif lower_name.endswith(".csv"):
            data = _read_csv(content)
        else:
            return {**empty_result, "errors": ["Unsupported file type. Upload .xlsx or .csv."]}
    except Exception as exc:  # pragma: no cover - defensive
        return {**empty_result, "errors": [f"Could not read file: {exc}"]}

    if not data or not any(str(value).strip() for row in data for value in row if value is not None):
        return {**empty_result, "errors": ["The file contains no rows."]}

    headers = [str(value).strip() if value is not None else "" for value in data[0]]
    password_column_indexes = {
        index for index, header in enumerate(headers)
        if _norm_header(header) in {"leaderpassword", "leaderloginpassword", "temporarypassword"}
    }
    mapping, header_errors = _detect_columns(headers)
    errors = list(header_errors)
    warnings: List[str] = []
    row_errors: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    if header_errors:
        return {**empty_result, "errors": errors, "detected_columns": mapping, "source_headers": headers}

    seen_teams: Dict[str, int] = {}
    seen_leaders: Dict[str, int] = {}
    seen_identities: Dict[str, Dict[str, Any]] = {}

    for row_idx, raw_row in enumerate(data[1:], start=2):
        cells = [str(value).strip() if value is not None else "" for value in (raw_row or [])]
        if not any(cells):
            continue

        def cell(family: str) -> str:
            index = mapping.get(family)
            return cells[index] if index is not None and index < len(cells) else ""

        team_name = cell("team_name")
        leader_name = cell("leader_name")
        leader_email = cell("leader_email").lower()
        messages: List[str] = []
        missing = [
            label for label, value in (
                ("team name", team_name),
                ("leader name", leader_name),
                ("leader email", leader_email),
            ) if not value
        ]
        if missing:
            messages.append(f"Missing required field(s): {', '.join(missing)}.")
        if leader_email and not _is_valid_email(leader_email):
            messages.append(f"Leader email '{leader_email}' is not a valid email.")

        previous_team_row = seen_teams.get(team_name.lower()) if team_name else None
        if previous_team_row is not None:
            messages.append(f"Team '{team_name}' already appears at row {previous_team_row}.")
        elif team_name:
            seen_teams[team_name.lower()] = row_idx

        previous_leader_row = seen_leaders.get(leader_email) if leader_email else None
        if previous_leader_row is not None:
            messages.append(f"Leader email '{leader_email}' already appears at row {previous_leader_row}.")
        elif leader_email:
            seen_leaders[leader_email] = row_idx

        members: List[Dict[str, str]] = []
        member_numbers = sorted(set(mapping["member_names"]) | set(mapping["member_emails"]))
        for number in member_numbers:
            name_index = mapping["member_names"].get(number)
            email_index = mapping["member_emails"].get(number)
            member_name = cells[name_index] if name_index is not None and name_index < len(cells) else ""
            member_email = cells[email_index].lower() if email_index is not None and email_index < len(cells) else ""
            if not member_name and not member_email:
                continue
            if member_email and not member_name:
                messages.append(f"Member {number} has an email but no name.")
            if member_email and not _is_valid_email(member_email):
                messages.append(f"Member {number} email '{member_email}' is not a valid email.")
            members.append({"name": member_name, "email": member_email})

        identities = [(leader_email, "leader")]
        identities.extend((member["email"], "member") for member in members if member["email"])
        row_identity_emails: set[str] = set()
        for identity_email, identity_role in identities:
            if not identity_email:
                continue
            if identity_email in row_identity_emails:
                messages.append(f"Email '{identity_email}' is reused within this team row.")
                continue
            row_identity_emails.add(identity_email)
            previous = seen_identities.get(identity_email)
            if previous and previous["row_number"] != row_idx:
                messages.append(
                    f"Email '{identity_email}' is already used as {previous['role']} for "
                    f"team '{previous['team_name']}' at row {previous['row_number']}."
                )
            else:
                seen_identities[identity_email] = {
                    "row_number": row_idx,
                    "team_name": team_name,
                    "role": identity_role,
                }

        if messages:
            for message in messages:
                errors.append(f"Row {row_idx}: {message}")
                row_errors.append({"row_number": row_idx, "message": message})
            continue

        rows.append({
            "row_number": row_idx,
            "team_name": team_name,
            "leader_name": leader_name,
            "leader_email": leader_email,
            "members": members,
            "warnings": [],
            "status": "new",
            "source_values": [
                "EXISTING ACCOUNT" if index in password_column_indexes and value else value
                for index, value in enumerate(cells)
            ],
        })

    return {
        "rows": rows,
        "warnings": warnings,
        "errors": errors,
        "row_errors": row_errors,
        "detected_columns": mapping,
        "source_headers": headers,
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


def build_registration_credential_workbook(
    filename: str,
    content: bytes,
    leader_credentials: Dict[int, Dict[str, str]],
) -> bytes:
    """Preserve the uploaded sheet and append login plus credential status."""
    from copy import copy
    from io import BytesIO
    from openpyxl import Workbook, load_workbook

    if filename.lower().endswith((".xlsx", ".xlsm")):
        workbook = load_workbook(BytesIO(content))
        sheet = workbook.active
    else:
        workbook = Workbook()
        sheet = workbook.active
        for row in _read_csv(content):
            sheet.append(row)

    for column in range(1, sheet.max_column + 1):
        if _norm_header(sheet.cell(row=1, column=column).value) in {
            "leaderpassword", "leaderloginpassword", "temporarypassword",
        }:
            for row_number in range(2, sheet.max_row + 1):
                sheet.cell(row=row_number, column=column, value="NOT EXPORTED")

    login_column = sheet.max_column + 1
    status_column = login_column + 1
    sheet.cell(row=1, column=login_column, value="Leader Login Email")
    sheet.cell(row=1, column=status_column, value="Credential Status")

    if login_column > 1:
        source_header = sheet.cell(row=1, column=login_column - 1)
        for column in (login_column, status_column):
            target = sheet.cell(row=1, column=column)
            target._style = copy(source_header._style)
            target.font = copy(source_header.font)
            target.fill = copy(source_header.fill)
            target.border = copy(source_header.border)
            target.alignment = copy(source_header.alignment)
            target.number_format = source_header.number_format

    for row_number, credential in leader_credentials.items():
        sheet.cell(row=row_number, column=login_column, value=credential["email"])
        sheet.cell(row=row_number, column=status_column, value=credential["status"])

    sheet.column_dimensions[sheet.cell(row=1, column=login_column).column_letter].width = 34
    sheet.column_dimensions[sheet.cell(row=1, column=status_column).column_letter].width = 24
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def build_registration_credential_csv(
    content: bytes,
    leader_credentials: Dict[int, Dict[str, str]],
) -> bytes:
    """Preserve CSV cell values and append login plus credential status."""
    source_rows = _read_csv(content)
    if not source_rows:
        return b""
    password_columns = {
        index for index, header in enumerate(source_rows[0])
        if _norm_header(header) in {"leaderpassword", "leaderloginpassword", "temporarypassword"}
    }
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([*source_rows[0], "Leader Login Email", "Credential Status"])
    for row_number, row in enumerate(source_rows[1:], start=2):
        row = ["NOT EXPORTED" if index in password_columns else value for index, value in enumerate(row)]
        credential = leader_credentials.get(row_number, {"email": "", "status": ""})
        writer.writerow([*row, credential["email"], credential["status"]])
    return output.getvalue().encode("utf-8-sig")


ASSIGNMENT_HEADERS = [
    "Round 1 Problem Number",
    "Round 1 Problem Title",
    "Round 1 Problem Description",
    "Round 1 Assignment Type",
    "Wildcard Problem Number",
    "Wildcard Problem Title",
    "Wildcard Problem Description",
    "Final Problem Number",
    "Final Problem Title",
    "Final Problem Description",
]


def build_registration_assignment_csv(headers: List[str], rows: List[List[Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def build_registration_assignment_workbook(headers: List[str], rows: List[List[Any]]) -> bytes:
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Participant Assignments"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        values = [str(cell.value or "") for cell in column]
        sheet.column_dimensions[column[0].column_letter].width = min(60, max(12, max(map(len, values), default=0) + 2))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()

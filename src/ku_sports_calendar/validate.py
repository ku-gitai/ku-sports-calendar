from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    event_count: int
    uids: list[str]


def _unfold(text: str) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in raw:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def validate_ics_text(text: str) -> ValidationResult:
    if not text.startswith("BEGIN:VCALENDAR\r\n"):
        raise ValueError("ICS must start with BEGIN:VCALENDAR using CRLF line endings")
    if not text.endswith("END:VCALENDAR\r\n"):
        raise ValueError("ICS must end with END:VCALENDAR and CRLF")
    for physical in text.split("\r\n"):
        if len(physical.encode("utf-8")) > 75:
            raise ValueError(f"ICS line exceeds 75 octets: {physical[:60]!r}")

    lines = _unfold(text)
    if lines.count("BEGIN:VCALENDAR") != 1 or lines.count("END:VCALENDAR") != 1:
        raise ValueError("ICS must contain exactly one VCALENDAR")
    if lines.count("BEGIN:VEVENT") != lines.count("END:VEVENT"):
        raise ValueError("Unbalanced VEVENT blocks")

    uids: list[str] = []
    event: list[str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            event = []
        elif line == "END:VEVENT":
            if event is None:
                raise ValueError("END:VEVENT without BEGIN:VEVENT")
            props = {x.split(":", 1)[0].split(";", 1)[0]: x.split(":", 1)[1] for x in event if ":" in x}
            for required in ("UID", "DTSTAMP", "DTSTART", "SUMMARY", "SEQUENCE"):
                if required not in props:
                    raise ValueError(f"VEVENT missing {required}")
            uids.append(props["UID"])
            event = None
        elif event is not None:
            event.append(line)

    if len(uids) != len(set(uids)):
        raise ValueError("Duplicate VEVENT UID detected")
    if not uids:
        raise ValueError("ICS contains no VEVENTs")
    return ValidationResult(event_count=len(uids), uids=uids)


def validate_file(path: str | Path) -> ValidationResult:
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        return validate_ics_text(f.read())

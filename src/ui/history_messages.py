from __future__ import annotations


STRUCTURED_HISTORY_KEYS = ("missing_folders", "export_failed", "watch_events")


def parse_structured_history_message(message: str) -> dict[str, str]:
    fields = {key: "" for key in STRUCTURED_HISTORY_KEYS}
    for part in str(message or "").split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        if key in fields:
            fields[key] = value.strip()
    return fields

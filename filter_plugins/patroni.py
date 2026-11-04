"""Filters for comparing the desired Patroni dynamic configuration with the running one."""

from __future__ import annotations


def patroni_strip_nulls(data):
    """Return a copy of data without keys whose value is None (recursively)."""
    if isinstance(data, dict):
        return {k: patroni_strip_nulls(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [patroni_strip_nulls(v) for v in data]
    return data


def _norm(value):
    # Patroni stores what it receives; YAML may give true/'on'/1 for the same setting.
    # Compare scalars as lowercase strings, keep structure for dicts/lists.
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        low = value.strip().lower()
        return {"true": "on", "false": "off", "yes": "on", "no": "off"}.get(low, value.strip())
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def _differs(current, desired) -> bool:
    if isinstance(desired, dict):
        if not isinstance(current, dict):
            return True
        for key, want in desired.items():
            if want is None:
                if key in current:
                    return True
                continue
            if key not in current or _differs(current[key], want):
                return True
        return False
    return _norm(current) != _norm(desired)


def patroni_dcs_differs(current, desired) -> bool:
    """True when applying desired via PATCH /config would change current.

    Keys absent from desired are left alone (PATCH merges); a None value means
    "the key must be absent"; lists (pg_hba) are compared as a whole.
    """
    return _differs(current or {}, desired or {})


class FilterModule:
    def filters(self):
        return {
            "__patroni_strip_nulls": patroni_strip_nulls,
            "patroni_strip_nulls": patroni_strip_nulls,
            "patroni_dcs_differs": patroni_dcs_differs,
        }

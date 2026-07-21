from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeEntry:
    category: str
    duration_minutes: int
    ownership_type: str

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    id: int
    name: str
    level: int
    exp: int

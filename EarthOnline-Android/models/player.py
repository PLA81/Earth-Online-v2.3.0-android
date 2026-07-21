from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Player:
    name: str
    account_level: int
    account_exp: int

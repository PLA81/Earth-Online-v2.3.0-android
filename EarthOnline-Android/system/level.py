from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpResult:
    level: int
    exp: int
    levels_gained: int


def exp_needed(level: int) -> int:
    """EXP needed to move from `level` to the next level."""
    return 100 + max(1, int(level)) * 50


def apply_exp(level: int, current_exp: int, amount: int) -> ExpResult:
    level = max(1, int(level))
    exp = max(0, int(current_exp)) + max(0, int(amount))
    original = level
    while exp >= exp_needed(level):
        exp -= exp_needed(level)
        level += 1
    return ExpResult(level=level, exp=exp, levels_gained=level - original)


def progress_percent(level: int, exp: int) -> int:
    needed = exp_needed(level)
    return min(100, round(max(0, exp) / needed * 100))

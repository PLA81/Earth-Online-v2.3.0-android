from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quest:
    id: int
    title: str
    role_name: str
    exp_reward: int
    status: str

from __future__ import annotations

from dataclasses import dataclass

from system.localization import ROLE_ATTRIBUTE, ROLE_DESCRIPTION, ROLE_DISPLAY


ROLE_META = {
    role: (ROLE_ATTRIBUTE[role], ROLE_DESCRIPTION[role])
    for role in ROLE_DISPLAY
}

CATEGORY_ROLE_MAP = {
    "research": "Scholar", "科研": "Scholar", "reading": "Scholar", "阅读": "Scholar",
    "paper": "Scholar", "论文": "Scholar", "python": "Scholar", "matlab": "Scholar",
    "writing": "Scholar", "写作": "Scholar", "学习": "Scholar", "课程": "Scholar",
    "focus": "Guardian", "专注": "Guardian", "planning": "Guardian", "计划": "Guardian",
    "整理": "Guardian", "复盘": "Guardian", "工作": "Guardian", "会议": "Guardian",
    "exercise": "Athlete", "运动": "Athlete", "walk": "Athlete", "步行": "Athlete",
    "run": "Athlete", "跑步": "Athlete", "strength": "Athlete", "力量": "Athlete",
    "meditation": "Mind", "冥想": "Mind", "recovery": "Mind", "恢复": "Mind",
    "rest": "Mind", "休息": "Mind", "睡眠": "Mind", "午睡": "Mind",
    "guitar": "Bard", "吉他": "Bard", "music": "Bard", "音乐": "Bard",
    "creative": "Bard", "创作": "Bard", "绘画": "Bard", "摄影": "Bard",
}

SKILL_KEYWORDS = {
    "Scholar": {
        "scholar_mathematics": ("数学", "math", "mathematics"),
        "scholar_python": ("python", "代码", "编程", "matlab"),
        "scholar_literature": ("阅读", "论文", "文献", "paper", "reading"),
        "scholar_writing": ("写作", "writing", "报告", "论文写作"),
        "scholar_deep_work": ("沟通", "汇报", "导师", "求助", "讨论", "communication", "help"),
    },
    "Guardian": {
        "guardian_focus": ("专注", "focus", "启动", "start", "工作"),
        "guardian_planning": ("计划", "planning", "复盘"),
        "guardian_digital": ("手机", "短视频", "digital", "video"),
        "guardian_order": ("整理", "秩序", "桌面", "order"),
        "guardian_command": ("恢复", "重新开始", "停止下滑", "归航", "recovery", "restart"),
    },
    "Athlete": {
        "athlete_strength": ("力量", "strength", "健身"),
        "athlete_cardio": ("跑步", "有氧", "cardio", "run"),
        "athlete_mobility": ("拉伸", "mobility", "瑜伽"),
        "athlete_walking": ("步行", "walk", "散步"),
        "athlete_recovery": ("恢复", "睡眠", "recovery"),
    },
    "Mind": {
        "mind_meditation": ("冥想", "meditation", "呼吸"),
        "mind_recovery": ("休息", "恢复", "rest", "午睡"),
        "mind_balance": ("情绪", "balance", "记录"),
        "mind_sleep": ("睡眠", "早睡", "sleep"),
        "mind_awareness": ("觉察", "mindful", "复盘"),
    },
    "Bard": {
        "bard_guitar": ("吉他", "guitar"),
        "bard_theory": ("乐理", "music theory"),
        "bard_creativity": ("创作", "creative", "作曲", "绘画"),
        "bard_performance": ("演奏", "performance", "录音"),
        "bard_expression": ("表达", "艺术", "expression", "摄影"),
    },
}

BOSS_WEAKNESS_KEYWORDS = {
    "DOPAMINE_DEMON": ("科研", "专注", "步行", "research", "focus", "walk", "手机", "学习"),
    "SLEEP_DRAGON": ("睡前", "睡眠", "早睡", "起床", "sleep", "手机"),
    "DISTRACTION_PHANTOM": ("专注", "整理", "单任务", "focus", "planning", "桌面", "工作"),
}


@dataclass(frozen=True)
class TimeReward:
    role_name: str | None
    exp: int


def role_for_text(text: str) -> str | None:
    lowered = text.casefold()
    for keyword, role in CATEGORY_ROLE_MAP.items():
        if keyword.casefold() in lowered:
            return role
    return None


def time_reward(category: str, minutes: int, owned: bool) -> TimeReward:
    if not owned:
        return TimeReward(None, 0)
    role = role_for_text(category)
    if role is None:
        return TimeReward(None, 0)
    minutes = max(0, int(minutes))
    exp = min(50, (minutes // 25) * 5)
    if minutes >= 10 and exp == 0:
        exp = 5
    return TimeReward(role, exp)


def quest_boss_damage(exp_reward: int, quest_title: str, boss_code: str) -> tuple[int, bool]:
    base = max(3, min(25, int(exp_reward) // 2))
    lowered = quest_title.casefold()
    weak = any(k.casefold() in lowered for k in BOSS_WEAKNESS_KEYWORDS.get(boss_code, ()))
    return (base + 4 if weak else base, weak)


def skill_code_for_action(role_name: str, text: str) -> str | None:
    lowered = text.casefold()
    mapping = SKILL_KEYWORDS.get(role_name, {})
    for code, keywords in mapping.items():
        if any(keyword.casefold() in lowered for keyword in keywords):
            return code
    return next(iter(mapping), None)


def character_class(role_name: str) -> str:
    return {
        "Scholar": "奥术学者",
        "Guardian": "秩序守卫",
        "Athlete": "生命先锋",
        "Mind": "澄明观者",
        "Bard": "共鸣吟游者",
    }.get(role_name, "现实旅者")

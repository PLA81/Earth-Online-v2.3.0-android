from __future__ import annotations

ROLE_NAMES = ("Scholar", "Guardian", "Athlete", "Mind", "Bard")

ROLE_DISPLAY = {
    "Scholar": "学者",
    "Guardian": "守护者",
    "Athlete": "行者",
    "Mind": "心灵者",
    "Bard": "吟游者",
}

ROLE_ATTRIBUTE = {
    "Scholar": "智识",
    "Guardian": "环境设计",
    "Athlete": "活力",
    "Mind": "澄明",
    "Bard": "创造",
}

ROLE_DESCRIPTION = {
    "Scholar": "知识生产、文献解码、数学推导、计算实验、写作与沟通。",
    "Guardian": "启动工程、环境设计、失控识别与恢复能力。",
    "Athlete": "力量、耐力、灵活性与身体恢复。",
    "Mind": "注意力、情绪平衡、冥想与休息。",
    "Bard": "音乐、艺术、游戏感与创造表达。",
}

QUEST_TYPE_DISPLAY = {
    "daily": "日常任务",
    "main": "主线任务",
    "sub": "支线任务",
    "hidden": "隐藏任务",
}

OWNERSHIP_DISPLAY = {
    "owned": "主动时间", "unowned": "无意识失控",
    "planned_done": "按计划完成", "intentional_change": "主动调整",
    "unrecorded": "未记录",
}

SOURCE_TYPE_DISPLAY = {
    "quest": "任务",
    "time": "整段时间记录",
    "half_hour": "半小时记录",
    "daily_bonus": "每日奖励",
    "boss_defeat": "首领胜利",
    "main_quest": "主线任务",
    "hidden_quest": "隐藏任务",
    "real_action": "现实行动",
    "action_start": "行动启动",
    "recovery": "恢复行动",
    "environment": "环境行动",
    "day_status": "每日状态",
}

EVENT_TITLE_TRANSLATIONS = {
    "QUEST COMPLETE": "任务完成",
    "ACCOUNT LEVEL UP": "账号升级",
    "SKILL UNLOCKED": "技能解锁",
    "SKILL MASTERY": "技能精进",
    "BOSS DEFEATED": "首领击败",
    "MAIN QUEST COMPLETE": "主线完成",
    "TIME RECORDED": "时间已记录",
    "STORY UNLOCKED": "剧情解锁",
    "ACHIEVEMENT UNLOCKED": "成就解锁",
}


def role_display(name: str | None) -> str:
    if not name:
        return "账号"
    return ROLE_DISPLAY.get(name, name)


def attribute_display(name: str | None) -> str:
    reverse = {
        "Intelligence": "智识",
        "Resolve": "意志",
        "Vitality": "活力",
        "Clarity": "澄明",
        "Creativity": "创造",
    }
    if not name:
        return "属性"
    return reverse.get(name, name)


def quest_type_display(value: str) -> str:
    return QUEST_TYPE_DISPLAY.get(value, value)


def ownership_display(value: str) -> str:
    return OWNERSHIP_DISPLAY.get(value, value)


def source_type_display(value: str) -> str:
    return SOURCE_TYPE_DISPLAY.get(value, value)

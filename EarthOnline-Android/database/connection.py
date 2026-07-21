from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from system.game_rules import (
    ROLE_META,
    character_class,
    quest_boss_damage,
    skill_code_for_action,
    time_reward,
)
from system.level import apply_exp
from system.localization import ROLE_DISPLAY, role_display
from system.time_window import TRACKING_START_SLOT, TRACKING_END_SLOT


ROLE_NAMES = ("Scholar", "Guardian", "Athlete", "Mind", "Bard")
NOW = lambda: datetime.now().isoformat(timespec="seconds")



LEGACY_SKILL_CODES = {
    "Mathematics": "scholar_mathematics",
    "Python": "scholar_python",
    "Literature": "scholar_literature",
    "Writing": "scholar_writing",
    "Focus": "guardian_focus",
    "Planning": "guardian_planning",
    "Digital Discipline": "guardian_digital",
    "Strength": "athlete_strength",
    "Cardio": "athlete_cardio",
    "Mobility": "athlete_mobility",
    "Meditation": "mind_meditation",
    "Recovery": "mind_recovery",
    "Emotional Balance": "mind_balance",
    "Guitar": "bard_guitar",
    "Music Theory": "bard_theory",
    "Creativity": "bard_creativity",
}

SKILL_DEFINITIONS: dict[str, tuple[tuple[str, str, str, int, int, str | None], ...]] = {
    "Scholar": (
        ("scholar_literature", "文献研读", "阅读、理解并整合高难度材料。", 1, 1, None),
        ("scholar_mathematics", "数学思维", "建立形式推理与定量直觉。", 1, 1, None),
        ("scholar_python", "科研编程", "把想法转化为可复现的计算工具。", 2, 3, "scholar_mathematics"),
        ("scholar_writing", "学术写作", "把研究转化为清晰、可检验的论证。", 2, 3, "scholar_literature"),
        ("scholar_deep_work", "深度科研", "长时间稳定地保持对同一研究问题的注意。", 3, 5, "scholar_python"),
    ),
    "Guardian": (
        ("guardian_focus", "专注启动", "主动开始，并保护当前唯一目标。", 1, 1, None),
        ("guardian_planning", "行动规划", "把抽象目标转换成下一步可执行动作。", 1, 1, None),
        ("guardian_digital", "数字自律", "管理高刺激数字环境与冲动使用。", 2, 3, "guardian_focus"),
        ("guardian_order", "环境秩序", "建立支持行动的物理与数字环境。", 2, 3, "guardian_planning"),
        ("guardian_command", "自我指挥", "即使动力不足，也能执行最小有效行动。", 3, 6, "guardian_digital"),
    ),
    "Athlete": (
        ("athlete_walking", "步行恢复", "用低门槛运动恢复能量与注意力。", 1, 1, None),
        ("athlete_mobility", "灵活性", "保持活动范围并减少身体紧张。", 1, 1, None),
        ("athlete_cardio", "有氧耐力", "建立可持续的心肺能力。", 2, 3, "athlete_walking"),
        ("athlete_strength", "力量训练", "构建力量、结构与韧性。", 2, 3, "athlete_mobility"),
        ("athlete_recovery", "身体恢复", "平衡训练负荷、睡眠与恢复。", 3, 6, "athlete_cardio"),
    ),
    "Mind": (
        ("mind_awareness", "自我觉察", "在反应之前看见注意力与情绪。", 1, 1, None),
        ("mind_recovery", "主动休息", "进行恢复性休息，而不是滑入逃避。", 1, 1, None),
        ("mind_meditation", "冥想训练", "通过刻意练习培养稳定注意。", 2, 3, "mind_awareness"),
        ("mind_balance", "情绪平衡", "从压力中恢复，同时不放弃整天。", 2, 3, "mind_recovery"),
        ("mind_sleep", "睡眠仪式", "建立稳定、高质量的入睡过渡。", 3, 5, "mind_balance"),
    ),
    "Bard": (
        ("bard_guitar", "吉他", "通过频繁而轻松的练习建立流畅度。", 1, 1, None),
        ("bard_creativity", "自由创作", "不过度评判地生成原创材料。", 1, 1, None),
        ("bard_theory", "音乐理论", "理解和声、节奏与音乐结构。", 2, 3, "bard_guitar"),
        ("bard_expression", "艺术表达", "通过艺术表达内在体验。", 2, 3, "bard_creativity"),
        ("bard_performance", "作品完成", "完成并呈现一个完整作品。", 3, 6, "bard_theory"),
    ),
}


class Database:
    """SQLite persistence and game-state engine for Earth Online v2.2.

    ``initialize`` is also the migration runner. It only adds columns/tables and
    seeds missing content, so a v0.1 database can be opened directly.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _columns(con: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}

    @classmethod
    def _ensure_column(cls, con: sqlite3.Connection, table: str, name: str, declaration: str) -> None:
        if name not in cls._columns(con, table):
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS player (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL DEFAULT 'Player',
                    account_level INTEGER NOT NULL DEFAULT 1,
                    account_exp INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    level INTEGER NOT NULL DEFAULT 1,
                    exp INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS quest_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    role_id INTEGER NOT NULL REFERENCES roles(id),
                    exp_reward INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    quest_type TEXT NOT NULL DEFAULT 'daily',
                    role_id INTEGER NOT NULL REFERENCES roles(id),
                    exp_reward INTEGER NOT NULL,
                    target_value INTEGER NOT NULL DEFAULT 1,
                    current_value INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    quest_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS time_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
                    ownership_type TEXT NOT NULL CHECK(ownership_type IN ('owned', 'unowned')),
                    entry_date TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role_id INTEGER NOT NULL REFERENCES roles(id),
                    name TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 1,
                    exp INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(role_id, name)
                );
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_value INTEGER NOT NULL,
                    current_value INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS main_quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bosses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    subtitle TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    max_hp INTEGER NOT NULL,
                    hp INTEGER NOT NULL,
                    weaknesses TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    defeated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS boss_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    boss_id INTEGER NOT NULL REFERENCES bosses(id),
                    hp_delta INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS world_regions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    progress INTEGER NOT NULL DEFAULT 0,
                    unlocked INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS world_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    region_id INTEGER NOT NULL REFERENCES world_regions(id),
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    current_value INTEGER NOT NULL DEFAULT 0,
                    target_value INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'locked',
                    metric_key TEXT NOT NULL DEFAULT 'manual',
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS story_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    chapter INTEGER NOT NULL DEFAULT 1,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_value INTEGER NOT NULL DEFAULT 1,
                    unlocked_at TEXT,
                    seen_at TEXT
                );
                CREATE TABLE IF NOT EXISTS npcs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    epithet TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    role_name TEXT,
                    affinity INTEGER NOT NULL DEFAULT 0,
                    unlock_type TEXT NOT NULL DEFAULT 'account_level',
                    unlock_value INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS npc_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    npc_id INTEGER NOT NULL REFERENCES npcs(id),
                    interaction_date TEXT NOT NULL,
                    dialogue TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(npc_id, interaction_date)
                );
                CREATE TABLE IF NOT EXISTS game_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS half_hour_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_date TEXT NOT NULL,
                    slot_index INTEGER NOT NULL CHECK(slot_index BETWEEN 0 AND 47),
                    category TEXT NOT NULL DEFAULT '',
                    ownership_type TEXT NOT NULL DEFAULT 'owned' CHECK(ownership_type IN ('owned','unowned')),
                    note TEXT NOT NULL DEFAULT '',
                    rewarded INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(record_date, slot_index)
                );
                CREATE TABLE IF NOT EXISTS daily_reward_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reward_date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    exp_reward INTEGER NOT NULL DEFAULT 0,
                    gold_reward INTEGER NOT NULL DEFAULT 0,
                    shield_reward INTEGER NOT NULL DEFAULT 0,
                    claimed_at TEXT NOT NULL,
                    UNIQUE(reward_date, code)
                );
                CREATE TABLE IF NOT EXISTS reward_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reward_date TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER,
                    role_name TEXT,
                    exp INTEGER NOT NULL DEFAULT 0,
                    gold INTEGER NOT NULL DEFAULT 0,
                    label TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                """
            )
            # Additive migration from v0.1.x.
            for table, name, declaration in (
                ("player", "gold", "INTEGER NOT NULL DEFAULT 0"),
                ("player", "title", "TEXT NOT NULL DEFAULT '地球新手'"),
                ("player", "active_boss_id", "INTEGER"),
                ("player", "total_exp", "INTEGER NOT NULL DEFAULT 0"),
                ("player", "last_login", "TEXT"),
                ("player", "streak_shields", "INTEGER NOT NULL DEFAULT 0"),
                ("roles", "attribute_name", "TEXT NOT NULL DEFAULT ''"),
                ("roles", "description", "TEXT NOT NULL DEFAULT ''"),
                ("quests", "story_text", "TEXT NOT NULL DEFAULT ''"),
                ("quests", "is_hidden", "INTEGER NOT NULL DEFAULT 0"),
                ("quests", "revealed", "INTEGER NOT NULL DEFAULT 1"),
                ("quests", "boss_damage", "INTEGER NOT NULL DEFAULT 0"),
                ("quests", "repeat_key", "TEXT"),
                ("skills", "code", "TEXT"),
                ("skills", "description", "TEXT NOT NULL DEFAULT ''"),
                ("skills", "tier", "INTEGER NOT NULL DEFAULT 1"),
                ("skills", "required_level", "INTEGER NOT NULL DEFAULT 1"),
                ("skills", "parent_id", "INTEGER"),
                ("skills", "unlocked_at", "TEXT"),
                ("achievements", "category", "TEXT NOT NULL DEFAULT 'General'"),
                ("achievements", "reward_title", "TEXT"),
                ("achievements", "hidden", "INTEGER NOT NULL DEFAULT 0"),
                ("main_quests", "chapter", "INTEGER NOT NULL DEFAULT 1"),
                ("main_quests", "reward_exp", "INTEGER NOT NULL DEFAULT 250"),
                ("main_quests", "status", "TEXT NOT NULL DEFAULT 'active'"),
                ("main_quests", "reward_claimed", "INTEGER NOT NULL DEFAULT 0"),
            ):
                self._ensure_column(con, table, name, declaration)
            con.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_quests_date ON quests(quest_date);
                CREATE INDEX IF NOT EXISTS idx_quests_type ON quests(quest_type);
                CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status);
                CREATE INDEX IF NOT EXISTS idx_time_entries_date ON time_entries(entry_date);
                CREATE INDEX IF NOT EXISTS idx_game_events_created ON game_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_half_hour_date ON half_hour_records(record_date, slot_index);
                CREATE INDEX IF NOT EXISTS idx_reward_ledger_date ON reward_ledger(reward_date);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_reward_source ON reward_ledger(source_type, source_id) WHERE source_id IS NOT NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_code ON skills(code) WHERE code IS NOT NULL;
                """
            )

        self._seed_defaults()
        self.ensure_daily_quests()
        self.refresh_all_progression()

    def _seed_defaults(self) -> None:
        now = NOW()
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO player(id, name, created_at) VALUES(1, 'Player', ?)", (now,))
            for role in ROLE_NAMES:
                con.execute("INSERT OR IGNORE INTO roles(name) VALUES(?)", (role,))
                attribute, description = ROLE_META[role]
                con.execute(
                    """UPDATE roles SET level=COALESCE(level,1), exp=COALESCE(exp,0),
                       attribute_name = ?, description = ? WHERE name = ?""",
                    (attribute, description, role),
                )
            con.execute("UPDATE player SET account_level=COALESCE(account_level,1), account_exp=COALESCE(account_exp,0) WHERE id=1")
            role_ids = {row["name"]: row["id"] for row in con.execute("SELECT id, name FROM roles")}

            templates = (
                ("科研 25 分钟", "Scholar", 10),
                ("阅读 10 页", "Scholar", 10),
                ("吉他 10 分钟", "Bard", 10),
                ("运动一次", "Athlete", 20),
                ("睡前不用手机", "Guardian", 10),
            )
            for title, role, reward in templates:
                con.execute(
                    """INSERT INTO quest_templates(title, role_id, exp_reward)
                       SELECT ?, ?, ? WHERE NOT EXISTS (
                           SELECT 1 FROM quest_templates WHERE title = ?
                       )""",
                    (title, role_ids[role], reward, title),
                )

            # 先为 v0.1 的英文技能补上稳定 code，再原地汉化，避免产生重复节点。
            for legacy_name, code in LEGACY_SKILL_CODES.items():
                if not con.execute("SELECT 1 FROM skills WHERE code=?", (code,)).fetchone():
                    con.execute(
                        "UPDATE skills SET code=? WHERE name=? AND code IS NULL",
                        (code, legacy_name),
                    )

            # 使用稳定的内部 code 原地汉化旧技能，避免产生重复节点。
            for role_name, definitions in SKILL_DEFINITIONS.items():
                for code, name, description, tier, required, _parent in definitions:
                    existing = con.execute(
                        "SELECT id FROM skills WHERE code=? OR (role_id=? AND name=?) ORDER BY code IS NOT NULL DESC LIMIT 1",
                        (code, role_ids[role_name], name),
                    ).fetchone()
                    if existing:
                        con.execute(
                            """UPDATE skills SET code=?, name=?, description=?, tier=?, required_level=? WHERE id=?""",
                            (code, name, description, tier, required, existing["id"]),
                        )
                    else:
                        con.execute(
                            """INSERT INTO skills(role_id, name, level, exp, code, description, tier, required_level)
                               VALUES(?, ?, 1, 0, ?, ?, ?, ?)""",
                            (role_ids[role_name], name, code, description, tier, required),
                        )
                for code, _name, _description, _tier, _required, parent_code in definitions:
                    if parent_code:
                        parent = con.execute("SELECT id FROM skills WHERE code=?", (parent_code,)).fetchone()
                        con.execute("UPDATE skills SET parent_id=? WHERE code=?", (parent["id"], code))

            achievements = (
                ("FIRST_QUEST", "初次行动", "完成第一个现实任务。", 1, "任务", "第一步", 0),
                ("THREE_IN_DAY", "今日冒险者", "在同一天完成三个任务。", 3, "任务", "破晓者", 0),
                ("RESEARCH_3_DAYS", "研究节奏", "在三个不同日期完成学者任务。", 3, "学者", "研究启程者", 0),
                ("EXERCISE_5", "身体觉醒", "累计完成五次行者任务。", 5, "行者", "觉醒之躯", 0),
                ("EXP_500", "成长开始", "累计获得 500 经验。", 500, "成长", "历练者", 0),
                ("STREAK_7", "七日火种", "连续七天完成至少一个现实行动。", 7, "守护者", "火种守护者", 0),
                ("LEVEL_5", "角色成形", "账号等级达到 5。", 5, "成长", "现实冒险者", 0),
                ("SKILL_5", "技能觉醒", "解锁五个技能节点。", 5, "技能", "织技者", 0),
                ("BOSS_1", "第一场胜利", "击败一个首领。", 1, "首领", "破魔者", 0),
                ("OWNERSHIP_3", "时间领主", "有三天时间所有权达到 80%。", 3, "时间", "时间拥有者", 0),
                ("WORLD_25", "地图展开", "任意人生区域推进到 25%。", 25, "世界", "开路者", 0),
                ("ALL_ROLES_3", "五路同行", "五个职业全部达到 3 级。", 3, "成长", "博学多面手", 0),
                ("FOCUS_CHAIN", "深度连段", "在半小时记录中完成连续四个主动时段。", 4, "专注", "深潜者", 0),
                ("CHEST_8", "史诗日", "一天内触发 8 次有效现实行动。", 8, "奖励", "势不可挡", 0),
            )
            for row in achievements:
                con.execute(
                    """INSERT INTO achievements(code, title, description, target_value, category, reward_title, hidden)
                       VALUES(?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(code) DO UPDATE SET title=excluded.title, description=excluded.description,
                       target_value=excluded.target_value, category=excluded.category,
                       reward_title=excluded.reward_title, hidden=excluded.hidden""",
                    row,
                )

            con.execute(
                """INSERT INTO main_quests(title, description, progress, chapter, reward_exp, status)
                   SELECT '恢复稳定科研能力', '通过稳定而可持续的行动重新建立科研节奏。', 0, 1, 250, 'active'
                   WHERE NOT EXISTS (SELECT 1 FROM main_quests)"""
            )

            bosses = (
                ("DOPAMINE_DEMON", "多巴胺恶魔", "无尽信息流", "它以无意识刷屏、即时刺激与逃避启动为食。", 120, "走路 · 手机离场 · 启动科研"),
                ("DISTRACTION_PHANTOM", "分心幽灵", "千页标签", "它把注意力切成碎片，让每件事都停留在未完成状态。", 150, "单任务 · 整理环境 · 完整专注块"),
                ("SLEEP_DRAGON", "睡眠巨龙", "深夜守门者", "每一次拖延入睡，都会让它的鳞片更加坚硬。", 180, "睡前不用手机 · 固定上床 · 晨间启动"),
            )
            for code, name, subtitle, description, hp, weaknesses in bosses:
                con.execute(
                    """INSERT INTO bosses(code, name, subtitle, description, max_hp, hp, weaknesses)
                       VALUES(?, ?, ?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET
                       name=excluded.name, subtitle=excluded.subtitle, description=excluded.description,
                       weaknesses=excluded.weaknesses""",
                    (code, name, subtitle, description, hp, hp, weaknesses),
                )
            if con.execute("SELECT active_boss_id FROM player WHERE id=1").fetchone()["active_boss_id"] is None:
                boss = con.execute("SELECT id FROM bosses WHERE code='DOPAMINE_DEMON'").fetchone()
                con.execute("UPDATE player SET active_boss_id=? WHERE id=1", (boss["id"],))

            regions = (
                ("ACADEMY", "学术前线", "从阅读、计算到原创研究的长期道路。", 1, 1),
                ("CITADEL", "自我城塞", "注意力、时间所有权与对反复模式的抵抗。", 0, 2),
                ("VITAL_WILDS", "生命旷野", "足以承载长期战役的身体与心灵。", 0, 3),
            )
            for code, title, description, unlocked, order in regions:
                con.execute(
                    """INSERT INTO world_regions(code, title, description, unlocked, sort_order)
                       VALUES(?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET
                       title=excluded.title, description=excluded.description, sort_order=excluded.sort_order""",
                    (code, title, description, unlocked, order),
                )
            region_ids = {r["code"]: r["id"] for r in con.execute("SELECT id, code FROM world_regions")}
            nodes = (
                ("ACADEMY", "RESEARCH_RHYTHM", "研究节奏", "完成学者任务，重建稳定科研动量。", 20, "scholar_quests", 1),
                ("ACADEMY", "PAPER_FORGE", "论文锻造炉", "通过具体里程碑推进当前论文。", 5, "manual", 2),
                ("ACADEMY", "MATH_TOWER", "数学高塔", "将学者提升到 8 级。", 8, "role:Scholar", 3),
                ("ACADEMY", "CODE_LAB", "代码实验室", "将科研编程技能提升到 5 级。", 5, "skill:scholar_python", 4),
                ("ACADEMY", "MENTOR_GATE", "导师之门", "完成当前主线任务。", 100, "main_progress", 5),
                ("CITADEL", "FOCUS_FLAME", "专注之焰", "维持十四天行动连击。", 14, "streak", 1),
                ("CITADEL", "DEMON_SEAL", "恶魔封印", "击败多巴胺恶魔。", 1, "boss:DOPAMINE_DEMON", 2),
                ("CITADEL", "PHANTOM_SEAL", "幽灵封印", "击败分心幽灵。", 1, "boss:DISTRACTION_PHANTOM", 3),
                ("CITADEL", "DRAGON_SEAL", "巨龙封印", "击败睡眠巨龙。", 1, "boss:SLEEP_DRAGON", 4),
                ("CITADEL", "TIME_KEEP", "时间要塞", "在七天中达到 80% 时间所有权。", 7, "ownership_days", 5),
                ("VITAL_WILDS", "MOVEMENT_TRAIL", "运动小径", "完成二十次行者任务。", 20, "athlete_quests", 1),
                ("VITAL_WILDS", "VITALITY_PEAK", "活力之巅", "将行者提升到 8 级。", 8, "role:Athlete", 2),
                ("VITAL_WILDS", "CLEAR_LAKE", "澄明之湖", "将心灵者提升到 8 级。", 8, "role:Mind", 3),
                ("VITAL_WILDS", "SONG_GROVE", "歌声林地", "将吟游者提升到 8 级。", 8, "role:Bard", 4),
            )
            for region, code, title, description, target, metric, order in nodes:
                con.execute(
                    """INSERT INTO world_nodes(region_id, code, title, description, target_value, metric_key, sort_order)
                       VALUES(?, ?, ?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET
                       title=excluded.title, description=excluded.description,
                       target_value=excluded.target_value, metric_key=excluded.metric_key,
                       sort_order=excluded.sort_order""",
                    (region_ids[region], code, title, description, target, metric, order),
                )

            stories = (
                ("PROLOGUE", 1, "登录：地球", "你在一个重复行动会塑造可见角色的世界中醒来。界面不是世界，你的下一次现实行动才是。", "account_level", 1),
                ("FIRST_STEP", 1, "第一道信号", "一个被完成的任务唤醒了沉睡系统。进步从此可以被看见。", "quest_count", 1),
                ("SKILL_AWAKEN", 2, "能力的枝桠", "一个技能节点被点亮。重复正在凝结为真正的能力。", "skill_unlocked", 5),
                ("BOSS_FALL", 2, "恶魔暂眠", "敌人没有消失，但它的模式已经减弱。道路暂时变得清晰。", "boss_defeated", 1),
                ("MAP_OPEN", 3, "世界展开", "人生地图的一片区域变得可读。远方里程碑第一次连成了路径。", "world_progress", 25),
                ("LEVEL_TEN", 4, "持续存在的角色", "你不再操纵一个原型角色。足够多的日子已经累积成历史。", "account_level", 10),
            )
            for story in stories:
                con.execute(
                    """INSERT INTO story_events(code, chapter, title, body, trigger_type, trigger_value)
                       VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET
                       chapter=excluded.chapter, title=excluded.title, body=excluded.body,
                       trigger_type=excluded.trigger_type, trigger_value=excluded.trigger_value""",
                    story,
                )

            npcs = (
                ("LYRA", "莱拉", "未竟思想的档案员", "帮助你把模糊的科研压力压缩成一个具体问题。", "Scholar", "account_level", 1),
                ("ATLAS", "阿特拉斯", "身体守护者", "提醒你：认知始终由真实身体承载。", "Athlete", "account_level", 2),
                ("ECHO", "回声", "静默屏幕的看守者", "研究让已击败首领再次回血的反复模式。", "Guardian", "boss_defeated", 1),
            )
            for npc in npcs:
                con.execute(
                    """INSERT INTO npcs(code, name, epithet, description, role_name, unlock_type, unlock_value)
                       VALUES(?, ?, ?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET
                       name=excluded.name, epithet=excluded.epithet, description=excluded.description,
                       role_name=excluded.role_name, unlock_type=excluded.unlock_type,
                       unlock_value=excluded.unlock_value""",
                    npc,
                )

            # One persistent side quest and two hidden quests.
            if not con.execute("SELECT 1 FROM quests WHERE quest_type='sub' LIMIT 1").fetchone():
                con.execute(
                    """INSERT INTO quests(title, quest_type, role_id, exp_reward, target_value,
                       current_value, quest_date, created_at, story_text)
                       VALUES('定义当前研究问题', 'sub', ?, 50, 3, 0, ?, ?,
                       '把模糊压力压缩成一个可以被实验或阅读推进的问题。')""",
                    (role_ids["Scholar"], date.today().isoformat(), now),
                )
            hidden = (
                ("连续行动 7 天", "HIDDEN_STREAK", 7, "保持火种：每天至少完成一个现实任务。"),
                ("连续 7 个活跃日不刷短视频", "HIDDEN_DOPAMINE", 7, "只有记录过活动的日期才计入；记录短视频会中断进度。"),
            )
            for title, key, target, story_text in hidden:
                if not con.execute("SELECT 1 FROM quests WHERE repeat_key=?", (key,)).fetchone():
                    con.execute(
                        """INSERT INTO quests(title, quest_type, role_id, exp_reward, target_value,
                           current_value, status, quest_date, created_at, story_text,
                           is_hidden, revealed, repeat_key)
                           VALUES(?, 'hidden', ?, 50, ?, 0, 'pending', ?, ?, ?, 1, 0, ?)""",
                        (title, role_ids["Guardian"], target, date.today().isoformat(), now, story_text, key),
                    )

            # 汉化旧版默认称号与已知系统事件，不改动玩家自定义内容。
            title_map = {
                "地球新手": "地球新手", "First Step": "第一步", "Daybreaker": "破晓者",
                "Research Initiate": "研究启程者", "Awakened Body": "觉醒之躯", "Experienced": "历练者",
                "Keeper of the Flame": "火种守护者", "Earth Online Adventurer": "现实冒险者",
                "Skill Weaver": "织技者", "Demon Breaker": "破魔者", "Time Owner": "时间拥有者",
                "Pathfinder": "开路者", "Polymath": "博学多面手",
            }
            current_title = con.execute("SELECT title FROM player WHERE id=1").fetchone()["title"]
            if current_title in title_map:
                con.execute("UPDATE player SET title=? WHERE id=1", (title_map[current_title],))
            event_map = {
                "任务完成": "任务完成", "账号升级": "账号升级", "技能解锁": "技能解锁",
                "技能精进": "技能精进", "首领击败": "首领击败", "主线完成": "主线完成",
                "时间已记录": "时间已记录", "剧情解锁": "剧情解锁", "成就解锁": "成就解锁",
            }
            for old, new_title in event_map.items():
                con.execute("UPDATE game_events SET title=? WHERE title=?", (new_title, old))

            # Recover total EXP when opening an older database.
            completed_exp = con.execute(
                "SELECT COALESCE(SUM(exp_reward), 0) AS value FROM quests WHERE status='completed'"
            ).fetchone()["value"]
            con.execute(
                "UPDATE player SET total_exp = MAX(total_exp, ?), last_login=? WHERE id=1",
                (int(completed_exp), now),
            )

            # 为旧存档补齐奖励流水，保证周报与导出能够统计升级前的数据。
            con.execute(
                """INSERT OR IGNORE INTO reward_ledger(
                       reward_date, source_type, source_id, role_name, exp, gold, label, created_at
                   )
                   SELECT COALESCE(NULLIF(SUBSTR(q.completed_at,1,10),''), q.quest_date),
                          'quest', q.id, r.name, q.exp_reward, 0, q.title,
                          COALESCE(q.completed_at, q.created_at)
                   FROM quests q JOIN roles r ON r.id=q.role_id
                   WHERE q.status='completed'"""
            )
            con.execute(
                """INSERT OR IGNORE INTO reward_ledger(
                       reward_date, source_type, source_id, role_name, exp, gold, label, created_at
                   )
                   SELECT t.entry_date, 'time', t.id,
                          CASE
                            WHEN LOWER(t.category) LIKE '%research%' OR t.category LIKE '%科研%' OR t.category LIKE '%阅读%' THEN 'Scholar'
                            WHEN LOWER(t.category) LIKE '%exercise%' OR t.category LIKE '%运动%' OR t.category LIKE '%跑步%' THEN 'Athlete'
                            WHEN LOWER(t.category) LIKE '%meditat%' OR t.category LIKE '%冥想%' OR t.category LIKE '%休息%' THEN 'Mind'
                            WHEN LOWER(t.category) LIKE '%guitar%' OR t.category LIKE '%吉他%' OR t.category LIKE '%音乐%' THEN 'Bard'
                            WHEN t.category LIKE '%整理%' OR t.category LIKE '%计划%' THEN 'Guardian'
                            ELSE NULL
                          END,
                          0, 0, t.category, t.created_at
                   FROM time_entries t"""
            )

    # ------------------------------------------------------------------
    # Basic player and quest methods
    # ------------------------------------------------------------------
    def ensure_daily_quests(self, day: date | None = None) -> None:
        day = day or date.today()
        with self.connect() as con:
            if con.execute(
                "SELECT 1 FROM quests WHERE quest_date=? AND quest_type='daily' AND status!='deleted' LIMIT 1",
                (day.isoformat(),),
            ).fetchone():
                return
            templates = con.execute(
                "SELECT title, role_id, exp_reward FROM quest_templates WHERE enabled=1 ORDER BY id"
            ).fetchall()
            con.executemany(
                """INSERT INTO quests(title, quest_type, role_id, exp_reward, quest_date, created_at)
                   VALUES(?, 'daily', ?, ?, ?, ?)""",
                [(r["title"], r["role_id"], r["exp_reward"], day.isoformat(), NOW()) for r in templates],
            )

    def get_player(self) -> sqlite3.Row:
        with self.connect() as con:
            return con.execute("SELECT * FROM player WHERE id=1").fetchone()

    def set_player_name(self, name: str) -> None:
        with self.connect() as con:
            con.execute("UPDATE player SET name=? WHERE id=1", ((name.strip()[:40] or "玩家"),))

    def get_roles(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM roles ORDER BY id").fetchall()

    def get_role(self, role_id: int) -> sqlite3.Row:
        with self.connect() as con:
            return con.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()

    def get_today_quests(self) -> list[sqlite3.Row]:
        self.ensure_daily_quests()
        return self.get_quests_by_type("daily")

    def get_quests_by_type(self, quest_type: str) -> list[sqlite3.Row]:
        with self.connect() as con:
            if quest_type == "daily":
                date_clause, args = "AND q.quest_date=?", (quest_type, date.today().isoformat())
            else:
                date_clause, args = "", (quest_type,)
            return con.execute(
                f"""SELECT q.*, r.name AS role_name FROM quests q
                    JOIN roles r ON r.id=q.role_id
                    WHERE q.quest_type=? {date_clause} AND q.status!='deleted'
                    ORDER BY CASE q.status WHEN 'pending' THEN 0 ELSE 1 END, q.id""",
                args,
            ).fetchall()

    def get_main_quests(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM main_quests WHERE active=1 OR status='completed' ORDER BY status='completed', id"
            ).fetchall()

    def get_main_quest(self) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM main_quests WHERE active=1 AND status='active' ORDER BY id LIMIT 1"
            ).fetchone()

    def add_quest(
        self,
        title: str,
        role_id: int,
        exp_reward: int,
        quest_type: str = "daily",
        target_value: int = 1,
        story_text: str = "",
    ) -> int:
        clean = title.strip()
        if not clean:
            raise ValueError("任务标题不能为空")
        if quest_type not in {"daily", "sub", "hidden"}:
            raise ValueError("无效的任务类型")
        with self.connect() as con:
            cur = con.execute(
                """INSERT INTO quests(title, quest_type, role_id, exp_reward, target_value,
                   quest_date, created_at, story_text, is_hidden, revealed)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clean[:100], quest_type, int(role_id), max(5, min(100, int(exp_reward))),
                    max(1, int(target_value)), date.today().isoformat(), NOW(), story_text[:300],
                    1 if quest_type == "hidden" else 0, 0 if quest_type == "hidden" else 1,
                ),
            )
            return int(cur.lastrowid)

    def delete_quest(self, quest_id: int) -> None:
        with self.connect() as con:
            con.execute("UPDATE quests SET status='deleted' WHERE id=? AND status='pending'", (quest_id,))

    def increment_quest_progress(self, quest_id: int, amount: int = 1) -> dict[str, Any]:
        with self.connect() as con:
            quest = con.execute("SELECT * FROM quests WHERE id=?", (quest_id,)).fetchone()
            if quest is None or quest["status"] != "pending":
                return {"completed": False, "already_completed": True}
            current = min(int(quest["target_value"]), int(quest["current_value"]) + max(1, int(amount)))
            con.execute("UPDATE quests SET current_value=?, revealed=1 WHERE id=?", (current, quest_id))
        if current >= int(quest["target_value"]):
            return self.complete_quest(quest_id)
        return {"completed": False, "current_value": current, "target_value": quest["target_value"]}

    def _add_event(
        self, con: sqlite3.Connection, event_type: str, title: str, message: str, payload: dict[str, Any] | None = None
    ) -> None:
        con.execute(
            "INSERT INTO game_events(event_type, title, message, payload, created_at) VALUES(?, ?, ?, ?, ?)",
            (event_type, title, message, json.dumps(payload or {}, ensure_ascii=False), NOW()),
        )

    def _log_reward(
        self,
        con: sqlite3.Connection,
        reward_date: str,
        source_type: str,
        source_id: int | None,
        role_name: str | None,
        exp: int,
        gold: int,
        label: str,
    ) -> None:
        con.execute(
            """INSERT OR IGNORE INTO reward_ledger(
                   reward_date, source_type, source_id, role_name, exp, gold, label, created_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (reward_date, source_type, source_id, role_name, int(exp), int(gold), label[:100], NOW()),
        )

    def _claim_daily_reward(
        self,
        con: sqlite3.Connection,
        reward_date: str,
        code: str,
        title: str,
        description: str,
        exp_reward: int = 0,
        gold_reward: int = 0,
        shield_reward: int = 0,
    ) -> dict[str, Any] | None:
        cur = con.execute(
            """INSERT OR IGNORE INTO daily_reward_claims(
                   reward_date, code, title, description, exp_reward, gold_reward, shield_reward, claimed_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (reward_date, code, title, description, exp_reward, gold_reward, shield_reward, NOW()),
        )
        if cur.rowcount == 0:
            return None
        if exp_reward:
            self._award_account_only(con, exp_reward)
        if gold_reward or shield_reward:
            con.execute(
                """UPDATE player SET gold=gold+?,
                   streak_shields=MIN(3, streak_shields+?) WHERE id=1""",
                (gold_reward, shield_reward),
            )
        self._log_reward(
            con, reward_date, "daily_bonus", int(cur.lastrowid), None,
            exp_reward, gold_reward, title,
        )
        self._add_event(
            con, "daily_reward", "奖励宝箱", title,
            {"code": code, "exp": exp_reward, "gold": gold_reward, "shield": shield_reward},
        )
        return {
            "code": code, "title": title, "description": description,
            "exp": exp_reward, "gold": gold_reward, "shield": shield_reward,
        }

    def _action_count(self, con: sqlite3.Connection, reward_date: str) -> int:
        quest_count = int(con.execute(
            "SELECT COUNT(*) c FROM quests WHERE quest_date=? AND status='completed'",
            (reward_date,),
        ).fetchone()["c"])
        slot_count = int(con.execute(
            """SELECT COUNT(*) c FROM half_hour_records
               WHERE record_date=? AND category<>'' AND ownership_type='owned'
               AND slot_index>=? AND slot_index<?""",
            (reward_date, TRACKING_START_SLOT, TRACKING_END_SLOT),
        ).fetchone()["c"])
        legacy_count = int(con.execute(
            """SELECT COUNT(*) c FROM time_entries
               WHERE entry_date=? AND ownership_type='owned'""",
            (reward_date,),
        ).fetchone()["c"])
        return quest_count + slot_count + legacy_count

    def _max_focus_chain(self, con: sqlite3.Connection, reward_date: str) -> int:
        rows = con.execute(
            """SELECT slot_index, category FROM half_hour_records
               WHERE record_date=? AND category<>'' AND ownership_type='owned'
               AND slot_index>=? AND slot_index<?
               ORDER BY slot_index""",
            (reward_date, TRACKING_START_SLOT, TRACKING_END_SLOT),
        ).fetchall()
        best = current = 0
        previous_slot: int | None = None
        previous_category = ""
        for row in rows:
            slot = int(row["slot_index"])
            category = row["category"].strip().casefold()
            if previous_slot is not None and slot == previous_slot + 1 and category == previous_category:
                current += 1
            else:
                current = 1
            best = max(best, current)
            previous_slot, previous_category = slot, category
        return best

    def _process_positive_rewards(self, con: sqlite3.Connection, reward_date: str) -> list[dict[str, Any]]:
        rewards: list[dict[str, Any]] = []
        actions = self._action_count(con, reward_date)
        milestones = (
            (1, "ACTION_1", "今日首胜宝箱", "第一次现实行动已经点燃今天。", 5, 10, 0),
            (3, "ACTION_3", "三连行动宝箱", "行动开始形成动量。", 10, 20, 0),
            (5, "ACTION_5", "深度冒险宝箱", "今天已经建立了可靠的行动节奏。", 20, 35, 1),
            (8, "ACTION_8", "史诗行动宝箱", "你正在把抽象目标压缩成连续现实动作。", 40, 60, 0),
            (12, "ACTION_12", "传奇日宝箱", "今天的角色已经留下清晰轨迹。", 75, 100, 0),
        )
        for threshold, code, title, desc, exp, gold, shield in milestones:
            if actions >= threshold:
                claimed = self._claim_daily_reward(con, reward_date, code, title, desc, exp, gold, shield)
                if claimed:
                    rewards.append(claimed)

        chain = self._max_focus_chain(con, reward_date)
        for threshold, exp, gold, title in (
            (2, 10, 10, "一小时专注连段"),
            (4, 30, 30, "两小时深度连段"),
            (6, 55, 55, "三小时沉浸连段"),
        ):
            if chain >= threshold:
                claimed = self._claim_daily_reward(
                    con, reward_date, f"FOCUS_{threshold}", title,
                    f"连续 {threshold} 个半小时保持同一主动活动。", exp, gold, 0,
                )
                if claimed:
                    rewards.append(claimed)

        role_counts = con.execute(
            """SELECT r.name, COUNT(*) c FROM quests q JOIN roles r ON r.id=q.role_id
               WHERE q.quest_date=? AND q.status='completed' GROUP BY r.name""",
            (reward_date,),
        ).fetchall()
        for row in role_counts:
            role = row["name"]
            count = int(row["c"])
            for threshold in (2, 4):
                if count >= threshold:
                    claimed = self._claim_daily_reward(
                        con, reward_date, f"ROLE_{role}_{threshold}",
                        f"{role_display(role)}专注连携 ×{threshold}",
                        f"今天完成 {threshold} 个{role_display(role)}任务。",
                        5 * threshold, 5 * threshold, 0,
                    )
                    if claimed:
                        rewards.append(claimed)

        daily = con.execute(
            """SELECT COUNT(*) total,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed
               FROM quests WHERE quest_date=? AND quest_type='daily' AND status!='deleted'""",
            (reward_date,),
        ).fetchone()
        if int(daily["total"] or 0) > 0 and int(daily["completed"] or 0) == int(daily["total"]):
            claimed = self._claim_daily_reward(
                con, reward_date, "DAILY_CLEAR", "今日任务全清",
                "所有日常任务均已完成。", 50, 50, 0,
            )
            if claimed:
                rewards.append(claimed)
        return rewards

    def get_daily_reward_state(self, day: date | None = None) -> dict[str, Any]:
        day = day or date.today()
        key = day.isoformat()
        with self.connect() as con:
            actions = self._action_count(con, key)
            chain = self._max_focus_chain(con, key)
            claimed = [dict(r) for r in con.execute(
                "SELECT * FROM daily_reward_claims WHERE reward_date=? ORDER BY id", (key,)
            ).fetchall()]
            player = con.execute("SELECT streak_shields FROM player WHERE id=1").fetchone()
        thresholds = (1, 3, 5, 8, 12)
        next_threshold = next((value for value in thresholds if actions < value), 12)
        if actions >= 12:
            label = "传奇状态"
        elif actions >= 8:
            label = "势不可挡"
        elif actions >= 5:
            label = "深度推进"
        elif actions >= 3:
            label = "动量已建立"
        elif actions >= 1:
            label = "今日已点火"
        else:
            label = "等待第一次行动"
        return {
            "actions": actions, "focus_chain": chain, "claimed": claimed,
            "next_threshold": next_threshold, "momentum": min(100, round(actions / 12 * 100)),
            "label": label, "streak_shields": int(player["streak_shields"] or 0),
        }

    def _award_account_only(self, con: sqlite3.Connection, amount: int) -> dict[str, int]:
        player = con.execute("SELECT * FROM player WHERE id=1").fetchone()
        result = apply_exp(player["account_level"], player["account_exp"], amount)
        con.execute(
            "UPDATE player SET account_level=?, account_exp=?, total_exp=total_exp+? WHERE id=1",
            (result.level, result.exp, amount),
        )
        if result.levels_gained:
            self._add_event(
                con, "account_level_up", "账号升级",
                f"账号等级 {player['account_level']} → {result.level}",
                {"level": result.level, "levels_gained": result.levels_gained},
            )
        return {"level": result.level, "levels_gained": result.levels_gained}

    def _unlock_eligible_skills(self, con: sqlite3.Connection, role_id: int) -> list[str]:
        role = con.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        rows = con.execute(
            "SELECT * FROM skills WHERE role_id=? AND unlocked_at IS NULL AND required_level<=? ORDER BY tier, id",
            (role_id, role["level"]),
        ).fetchall()
        unlocked: list[str] = []
        for row in rows:
            # Parent must already be unlocked, except root nodes.
            if row["parent_id"] is not None:
                parent = con.execute("SELECT unlocked_at FROM skills WHERE id=?", (row["parent_id"],)).fetchone()
                if parent is None or parent["unlocked_at"] is None:
                    continue
            con.execute("UPDATE skills SET unlocked_at=? WHERE id=?", (NOW(), row["id"]))
            unlocked.append(row["name"])
            self._add_event(
                con, "skill_unlock", "技能解锁", f"{role_display(role['name'])} · {row['name']}",
                {"role": role["name"], "skill": row["name"]},
            )
        return unlocked

    def _apply_skill_exp(
        self, con: sqlite3.Connection, role: sqlite3.Row, text: str, amount: int
    ) -> dict[str, Any] | None:
        code = skill_code_for_action(role["name"], text)
        skill = con.execute("SELECT * FROM skills WHERE code=?", (code,)).fetchone() if code else None
        if skill is None or skill["unlocked_at"] is None:
            skill = con.execute(
                "SELECT * FROM skills WHERE role_id=? AND unlocked_at IS NOT NULL ORDER BY tier, id LIMIT 1",
                (role["id"],),
            ).fetchone()
        if skill is None:
            return None
        exp = int(skill["exp"]) + max(1, amount // 2)
        level = int(skill["level"])
        original = level
        while exp >= 75 + level * 25:
            exp -= 75 + level * 25
            level += 1
        con.execute("UPDATE skills SET level=?, exp=? WHERE id=?", (level, exp, skill["id"]))
        if level > original:
            self._add_event(
                con, "skill_level_up", "技能精进", f"{skill['name']} {original} 级 → {level} 级",
                {"skill": skill["name"], "level": level},
            )
        return {"name": skill["name"], "level": level, "levels_gained": level - original, "exp": exp}

    def _award_role_exp(
        self, con: sqlite3.Connection, role_id: int, amount: int, action_text: str
    ) -> dict[str, Any]:
        role = con.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        player = con.execute("SELECT * FROM player WHERE id=1").fetchone()
        role_result = apply_exp(role["level"], role["exp"], amount)
        account_result = apply_exp(player["account_level"], player["account_exp"], amount)
        con.execute("UPDATE roles SET level=?, exp=? WHERE id=?", (role_result.level, role_result.exp, role_id))
        con.execute(
            "UPDATE player SET account_level=?, account_exp=?, total_exp=total_exp+? WHERE id=1",
            (account_result.level, account_result.exp, amount),
        )
        if role_result.levels_gained:
            self._add_event(
                con, "role_level_up", f"{role_display(role['name'])}升级",
                f"{role['level']} 级 → {role_result.level} 级",
                {"role": role["name"], "level": role_result.level},
            )
        if account_result.levels_gained:
            self._add_event(
                con, "account_level_up", "账号升级",
                f"账号等级 {player['account_level']} → {account_result.level}",
                {"level": account_result.level},
            )
        # Re-read role so skill unlock rules see the new level.
        updated_role = con.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        unlocked = self._unlock_eligible_skills(con, role_id)
        skill = self._apply_skill_exp(con, updated_role, action_text, amount)
        return {
            "role_name": role["name"], "role_level": role_result.level,
            "role_levels_gained": role_result.levels_gained,
            "account_level": account_result.level,
            "account_levels_gained": account_result.levels_gained,
            "unlocked_skills": unlocked, "skill": skill,
        }

    def _apply_boss_delta(
        self,
        con: sqlite3.Connection,
        delta: int,
        source_type: str,
        source_id: int | None,
        note: str,
    ) -> dict[str, Any] | None:
        player = con.execute("SELECT active_boss_id FROM player WHERE id=1").fetchone()
        if not player or player["active_boss_id"] is None:
            return None
        boss = con.execute("SELECT * FROM bosses WHERE id=?", (player["active_boss_id"],)).fetchone()
        if boss is None:
            return None
        if boss["status"] == "defeated" and delta < 0:
            return {"name": boss["name"], "hp": 0, "max_hp": boss["max_hp"], "delta": 0, "defeated": True}
        new_hp = max(0, min(int(boss["max_hp"]), int(boss["hp"]) + int(delta)))
        defeated_now = new_hp == 0 and boss["status"] != "defeated"
        status = "defeated" if new_hp == 0 else "active"
        con.execute(
            "UPDATE bosses SET hp=?, status=?, defeated_at=? WHERE id=?",
            (new_hp, status, NOW() if defeated_now else boss["defeated_at"], boss["id"]),
        )
        boss_event = con.execute(
            "INSERT INTO boss_events(boss_id, hp_delta, source_type, source_id, note, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (boss["id"], new_hp - int(boss["hp"]), source_type, source_id, note[:200], NOW()),
        )
        if defeated_now:
            self._award_account_only(con, 100)
            con.execute("UPDATE player SET gold=gold+100 WHERE id=1")
            self._log_reward(
                con, date.today().isoformat(), "boss_defeat", int(boss_event.lastrowid),
                None, 100, 100, f"击败首领：{boss['name']}",
            )
            self._add_event(
                con, "boss_defeated", "首领击败", f"{boss['name']}进入休眠。+100 经验 · +100 金币",
                {"boss": boss["name"]},
            )
            next_boss = con.execute(
                "SELECT id FROM bosses WHERE status!='defeated' AND id!=? ORDER BY id LIMIT 1", (boss["id"],)
            ).fetchone()
            if next_boss:
                con.execute("UPDATE player SET active_boss_id=? WHERE id=1", (next_boss["id"],))
            else:
                con.execute("UPDATE player SET active_boss_id=NULL WHERE id=1")
        return {
            "name": boss["name"], "code": boss["code"], "hp": new_hp, "max_hp": boss["max_hp"],
            "delta": new_hp - int(boss["hp"]), "defeated": defeated_now, "status": status,
        }

    def _claim_completed_main_quests(self, con: sqlite3.Connection) -> list[str]:
        claimed: list[str] = []
        rows = con.execute(
            "SELECT * FROM main_quests WHERE status='completed' AND reward_claimed=0"
        ).fetchall()
        for row in rows:
            self._award_account_only(con, int(row["reward_exp"]))
            con.execute(
                "UPDATE player SET gold=gold+? WHERE id=1",
                (max(25, int(row["reward_exp"]) // 2),),
            )
            con.execute("UPDATE main_quests SET reward_claimed=1 WHERE id=?", (row["id"],))
            main_gold = max(25, int(row["reward_exp"]) // 2)
            self._log_reward(
                con, date.today().isoformat(), "main_quest", int(row["id"]), None,
                int(row["reward_exp"]), main_gold, f"主线完成：{row['title']}",
            )
            self._add_event(
                con, "main_quest_complete", "主线完成", row["title"],
                {"reward_exp": row["reward_exp"]},
            )
            claimed.append(row["title"])
        return claimed

    def complete_quest(self, quest_id: int) -> dict[str, Any]:
        with self.connect() as con:
            quest = con.execute("SELECT * FROM quests WHERE id=?", (quest_id,)).fetchone()
            if quest is None:
                raise ValueError("任务不存在")
            if quest["status"] != "pending":
                return {"already_completed": True}
            role = con.execute("SELECT * FROM roles WHERE id=?", (quest["role_id"],)).fetchone()
            reward = int(quest["exp_reward"])
            progression = self._award_role_exp(con, role["id"], reward, quest["title"])
            boss = con.execute(
                "SELECT b.* FROM bosses b JOIN player p ON p.active_boss_id=b.id WHERE p.id=1"
            ).fetchone()
            damage, weakness = quest_boss_damage(reward, quest["title"], boss["code"]) if boss else (0, False)
            boss_result = self._apply_boss_delta(con, -damage, "quest", quest_id, quest["title"]) if damage else None
            completed_at = NOW()
            con.execute(
                """UPDATE quests SET status='completed', current_value=target_value,
                   completed_at=?, boss_damage=? WHERE id=?""",
                (completed_at, damage, quest_id),
            )
            self._log_reward(
                con, date.today().isoformat(), "quest", quest_id, role["name"], reward, 0, quest["title"]
            )
            if role["name"] == "Scholar":
                con.execute(
                    """UPDATE main_quests SET progress=MIN(100, progress+?),
                       status=CASE WHEN progress+?>=100 THEN 'completed' ELSE status END
                       WHERE active=1 AND status='active'""",
                    (max(1, reward // 5), max(1, reward // 5)),
                )
            main_completed = self._claim_completed_main_quests(con)
            self._add_event(
                con, "quest_complete", "任务完成",
                f"{quest['title']} · {role_display(role['name'])} +{reward} 经验",
                {"quest_id": quest_id, "role": role["name"], "reward": reward},
            )
            positive_rewards = self._process_positive_rewards(con, date.today().isoformat())

        hidden_unlocked = self.refresh_hidden_quests()
        unlocked_achievements = self.refresh_achievements()
        self.refresh_world_progress()
        unlocked_story = self.refresh_story_events()
        return {
            "already_completed": False,
            "quest_title": quest["title"], "role_name": role["name"], "reward": reward,
            **progression, "boss": boss_result, "weakness": weakness,
            "hidden_completed": hidden_unlocked, "main_completed": main_completed,
            "unlocked_achievements": unlocked_achievements,
            "unlocked_story": unlocked_story,
            "positive_rewards": positive_rewards,
        }

    # ------------------------------------------------------------------
    # Time, streak and analytics
    # ------------------------------------------------------------------
    def add_time_entry(self, category: str, duration_minutes: int, ownership_type: str) -> dict[str, Any]:
        clean = category.strip()
        duration = int(duration_minutes)
        if not clean:
            raise ValueError("时间分类不能为空")
        if duration <= 0 or duration > 1440:
            raise ValueError("时长必须在 1 到 1440 分钟之间")
        if ownership_type not in {"owned", "unowned"}:
            raise ValueError("无效的时间所有权类型")
        today = date.today().isoformat()
        with self.connect() as con:
            cur = con.execute(
                """INSERT INTO time_entries(category, duration_minutes, ownership_type, entry_date, created_at)
                   VALUES(?, ?, ?, ?, ?)""",
                (clean[:50], duration, ownership_type, today, NOW()),
            )
            entry_id = int(cur.lastrowid)
            reward = time_reward(clean, duration, ownership_type == "owned")
            progression = None
            if reward.role_name and reward.exp:
                role = con.execute("SELECT * FROM roles WHERE name=?", (reward.role_name,)).fetchone()
                progression = self._award_role_exp(con, role["id"], reward.exp, clean)
            delta = -max(1, min(15, duration // 15)) if ownership_type == "owned" else max(1, min(20, duration // 10))
            boss_result = self._apply_boss_delta(con, delta, "time", entry_id, clean)
            self._log_reward(con, today, "time", entry_id, reward.role_name, reward.exp, 0, clean)
            self._add_event(
                con, "time_log", "时间已记录",
                f"{clean} · {duration} 分钟 · {'主动时间' if ownership_type == 'owned' else '失控时间'}",
                {"minutes": duration, "ownership": ownership_type},
            )
            positive_rewards = self._process_positive_rewards(con, today)
        self.refresh_hidden_quests()
        self.refresh_achievements()
        self.refresh_world_progress()
        self.refresh_story_events()
        return {
            "id": entry_id, "exp": reward.exp, "role_name": reward.role_name,
            "progression": progression, "boss": boss_result,
            "positive_rewards": positive_rewards,
        }

    def get_today_time_entries(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM time_entries WHERE entry_date=? ORDER BY id DESC", (date.today().isoformat(),)
            ).fetchall()

    @staticmethod
    def slot_label(slot_index: int) -> str:
        slot = max(0, min(48, int(slot_index)))
        minutes = slot * 30
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def get_half_hour_records(self, day: date | None = None) -> list[dict[str, Any]]:
        day = day or date.today()
        with self.connect() as con:
            rows = {
                int(row["slot_index"]): dict(row)
                for row in con.execute(
                    "SELECT * FROM half_hour_records WHERE record_date=? ORDER BY slot_index",
                    (day.isoformat(),),
                ).fetchall()
            }
        result: list[dict[str, Any]] = []
        for slot in range(48):
            row = rows.get(slot, {})
            result.append({
                "id": row.get("id"), "record_date": day.isoformat(), "slot_index": slot,
                "start_time": self.slot_label(slot), "end_time": self.slot_label(slot + 1),
                "category": row.get("category", ""),
                "ownership_type": row.get("ownership_type", "owned"),
                "note": row.get("note", ""), "rewarded": int(row.get("rewarded", 0) or 0),
            })
        return result

    def upsert_half_hour_record(
        self,
        slot_index: int,
        category: str,
        ownership_type: str = "owned",
        note: str = "",
        day: date | None = None,
    ) -> dict[str, Any]:
        day = day or date.today()
        key = day.isoformat()
        slot = int(slot_index)
        if slot < 0 or slot > 47:
            raise ValueError("半小时槽位必须在 0 到 47 之间")
        clean = category.strip()[:60]
        if ownership_type not in {"owned", "unowned"}:
            raise ValueError("无效的时间所有权类型")
        if not clean:
            self.clear_half_hour_record(slot, day)
            return {"cleared": True, "slot_index": slot, "positive_rewards": []}
        with self.connect() as con:
            existing = con.execute(
                "SELECT * FROM half_hour_records WHERE record_date=? AND slot_index=?", (key, slot)
            ).fetchone()
            was_rewarded = bool(existing and existing["rewarded"])
            if existing:
                con.execute(
                    """UPDATE half_hour_records SET category=?, ownership_type=?, note=?, updated_at=?
                       WHERE id=?""",
                    (clean, ownership_type, note.strip()[:300], NOW(), existing["id"]),
                )
                record_id = int(existing["id"])
            else:
                cur = con.execute(
                    """INSERT INTO half_hour_records(
                           record_date, slot_index, category, ownership_type, note, rewarded, created_at, updated_at
                       ) VALUES(?, ?, ?, ?, ?, 0, ?, ?)""",
                    (key, slot, clean, ownership_type, note.strip()[:300], NOW(), NOW()),
                )
                record_id = int(cur.lastrowid)
            exp = 0
            role_name: str | None = None
            progression = None
            boss_result = None
            if not was_rewarded:
                reward = time_reward(clean, 30, ownership_type == "owned")
                exp, role_name = reward.exp, reward.role_name
                if role_name and exp:
                    role = con.execute("SELECT * FROM roles WHERE name=?", (role_name,)).fetchone()
                    progression = self._award_role_exp(con, role["id"], exp, clean)
                delta = -2 if ownership_type == "owned" else 3
                boss_result = self._apply_boss_delta(con, delta, "half_hour", record_id, clean)
                con.execute("UPDATE half_hour_records SET rewarded=1 WHERE id=?", (record_id,))
                self._log_reward(con, key, "half_hour", record_id, role_name, exp, 0, clean)
                self._add_event(
                    con, "half_hour_log", "半小时已记录",
                    f"{self.slot_label(slot)} · {clean} · {'主动时间' if ownership_type == 'owned' else '失控时间'}",
                    {"slot": slot, "ownership": ownership_type},
                )
            positive_rewards = self._process_positive_rewards(con, key)
        self.refresh_hidden_quests()
        self.refresh_achievements()
        self.refresh_world_progress()
        self.refresh_story_events()
        return {
            "id": record_id, "slot_index": slot, "exp": exp, "role_name": role_name,
            "progression": progression, "boss": boss_result, "positive_rewards": positive_rewards,
            "already_rewarded": was_rewarded,
        }

    def clear_half_hour_record(self, slot_index: int, day: date | None = None) -> None:
        day = day or date.today()
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM half_hour_records WHERE record_date=? AND slot_index=?",
                (day.isoformat(), int(slot_index)),
            ).fetchone()
            if row:
                con.execute(
                    """UPDATE half_hour_records SET category='', note='', ownership_type='owned', updated_at=?
                       WHERE id=?""",
                    (NOW(), row["id"]),
                )

    def get_daily_reward_history(self, day: date | None = None) -> list[sqlite3.Row]:
        day = day or date.today()
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM daily_reward_claims WHERE reward_date=? ORDER BY id", (day.isoformat(),)
            ).fetchall()

    def get_reward_ledger(self, start: date, end: date) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT * FROM reward_ledger WHERE reward_date BETWEEN ? AND ?
                   ORDER BY reward_date, id""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()

    def get_streak(self) -> int:
        with self.connect() as con:
            rows = con.execute(
                "SELECT DISTINCT quest_date FROM quests WHERE status='completed' ORDER BY quest_date DESC"
            ).fetchall()
        completed = {date.fromisoformat(r["quest_date"]) for r in rows}
        if not completed:
            return 0
        cursor = date.today()
        if cursor not in completed:
            cursor -= timedelta(days=1)
        streak = 0
        while cursor in completed:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def get_today_summary(self) -> dict[str, int]:
        today = date.today().isoformat()
        with self.connect() as con:
            q = con.execute(
                """SELECT COUNT(*) total,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                   COALESCE(SUM(CASE WHEN status='completed' THEN exp_reward ELSE 0 END),0) exp
                   FROM quests WHERE quest_date=? AND quest_type='daily' AND status!='deleted'""",
                (today,),
            ).fetchone()
            legacy = con.execute(
                """SELECT COALESCE(SUM(duration_minutes),0) total,
                   COALESCE(SUM(CASE WHEN ownership_type='owned' THEN duration_minutes ELSE 0 END),0) owned
                   FROM time_entries WHERE entry_date=?""",
                (today,),
            ).fetchone()
            slots = con.execute(
                """SELECT COUNT(*) total_slots,
                   COALESCE(SUM(CASE WHEN ownership_type='owned' THEN 1 ELSE 0 END),0) owned_slots
                   FROM half_hour_records WHERE record_date=? AND category<>''
                   AND slot_index>=? AND slot_index<?""",
                (today, TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchone()
            ledger = con.execute(
                "SELECT COALESCE(SUM(exp),0) exp, COALESCE(SUM(gold),0) gold FROM reward_ledger WHERE reward_date=?",
                (today,),
            ).fetchone()
        total = int(legacy["total"]) + int(slots["total_slots"] or 0) * 30
        owned = int(legacy["owned"]) + int(slots["owned_slots"] or 0) * 30
        state = self.get_daily_reward_state()
        return {
            "quest_total": int(q["total"] or 0), "quest_completed": int(q["completed"] or 0),
            "today_exp": int(ledger["exp"] or q["exp"] or 0), "today_gold": int(ledger["gold"] or 0),
            "time_total": total, "time_owned": owned,
            "ownership": round(owned / total * 100) if total else 0, "streak": self.get_streak(),
            "actions": int(state["actions"]), "momentum": int(state["momentum"]),
            "focus_chain": int(state["focus_chain"]), "streak_shields": int(state["streak_shields"]),
        }

    def get_weekly_stats(self, days: int = 7, end_day: date | None = None) -> dict[str, Any]:
        end = end_day or date.today()
        start = end - timedelta(days=days - 1)
        with self.connect() as con:
            categories = con.execute(
                """SELECT category, SUM(minutes) minutes FROM (
                       SELECT category, duration_minutes minutes FROM time_entries
                       WHERE entry_date BETWEEN ? AND ?
                       UNION ALL
                       SELECT category, 30 minutes FROM half_hour_records
                       WHERE record_date BETWEEN ? AND ? AND category<>''
                       AND slot_index>=? AND slot_index<?
                   ) GROUP BY category ORDER BY minutes DESC""",
                (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat(),
                 TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchall()
            daily_quests = {
                row["quest_date"]: dict(row) for row in con.execute(
                    """SELECT quest_date,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                       SUM(CASE WHEN status!='deleted' THEN 1 ELSE 0 END) total
                       FROM quests WHERE quest_type='daily' AND quest_date BETWEEN ? AND ?
                       GROUP BY quest_date ORDER BY quest_date""",
                    (start.isoformat(), end.isoformat()),
                ).fetchall()
            }
            daily_time_rows = con.execute(
                """SELECT day, SUM(minutes) total,
                   SUM(CASE WHEN ownership='owned' THEN minutes ELSE 0 END) owned
                   FROM (
                       SELECT entry_date day, duration_minutes minutes, ownership_type ownership
                       FROM time_entries WHERE entry_date BETWEEN ? AND ?
                       UNION ALL
                       SELECT record_date day, 30 minutes, ownership_type ownership
                       FROM half_hour_records WHERE record_date BETWEEN ? AND ? AND category<>''
                       AND slot_index>=? AND slot_index<?
                   ) GROUP BY day""",
                (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat(),
                 TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchall()
            daily_time = {row["day"]: dict(row) for row in daily_time_rows}
            role_exp = con.execute(
                """SELECT r.name, COALESCE(SUM(l.exp),0) exp
                   FROM roles r LEFT JOIN reward_ledger l ON l.role_name=r.name
                   AND l.reward_date BETWEEN ? AND ? GROUP BY r.id ORDER BY r.id""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            ledger = con.execute(
                """SELECT COALESCE(SUM(exp),0) exp, COALESCE(SUM(gold),0) gold
                   FROM reward_ledger WHERE reward_date BETWEEN ? AND ?""",
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            marks = con.execute(
                """SELECT COALESCE(SUM(shield_reward),0) value FROM daily_reward_claims
                   WHERE reward_date BETWEEN ? AND ?""",
                (start.isoformat(), end.isoformat()),
            ).fetchone()
        daily: list[dict[str, Any]] = []
        cursor = start
        total_minutes = owned_minutes = 0
        while cursor <= end:
            key = cursor.isoformat()
            q = daily_quests.get(key, {})
            t = daily_time.get(key, {})
            total = int(t.get("total", 0) or 0)
            owned = int(t.get("owned", 0) or 0)
            total_minutes += total
            owned_minutes += owned
            daily.append({
                "quest_date": key, "completed": int(q.get("completed", 0) or 0),
                "total": int(q.get("total", 0) or 0), "minutes": total, "owned_minutes": owned,
                "ownership": round(owned / total * 100) if total else 0,
            })
            cursor += timedelta(days=1)
        return {
            "start": start, "end": end, "categories": [dict(r) for r in categories],
            "daily": daily, "role_exp": [dict(r) for r in role_exp],
            "ownership": round(owned_minutes / total_minutes * 100) if total_minutes else 0,
            "total_minutes": total_minutes, "total_exp": int(ledger["exp"] or 0),
            "total_gold": int(ledger["gold"] or 0),
            "total_marks": int(marks["value"] or 0),
        }

    # ------------------------------------------------------------------
    # Skills and character
    # ------------------------------------------------------------------
    def get_skills_grouped(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """SELECT r.id role_id, r.name role_name, r.level role_level, r.attribute_name,
                   s.id skill_id, s.code, s.name skill_name, s.level skill_level, s.exp skill_exp,
                   s.description, s.tier, s.required_level, s.parent_id, s.unlocked_at
                   FROM roles r LEFT JOIN skills s ON s.role_id=r.id ORDER BY r.id, s.tier, s.id"""
            ).fetchall()
        grouped: list[dict[str, Any]] = []
        for role in self.get_roles():
            skill_rows = [r for r in rows if r["role_id"] == role["id"] and r["skill_id"] is not None]
            grouped.append(
                {
                    "role_id": role["id"], "role_name": role["name"], "role_level": role["level"],
                    "attribute_name": role["attribute_name"], "skills": [dict(r) for r in skill_rows],
                }
            )
        return grouped

    def get_character_profile(self) -> dict[str, Any]:
        player = dict(self.get_player())
        roles = [dict(r) for r in self.get_roles()]
        highest = max(roles, key=lambda r: (int(r["level"]), -int(r["id"])))
        with self.connect() as con:
            skill_rows = con.execute(
                """SELECT role_id,
                          SUM(CASE WHEN unlocked_at IS NOT NULL THEN 1 ELSE 0 END) unlocked_count,
                          SUM(CASE WHEN unlocked_at IS NOT NULL AND level >= 2 THEN 1 ELSE 0 END) mastered_count
                   FROM skills GROUP BY role_id"""
            ).fetchall()
            skill_meta = {
                int(row["role_id"]): {
                    "unlocked": int(row["unlocked_count"] or 0),
                    "mastered": int(row["mastered_count"] or 0),
                }
                for row in skill_rows
            }
            unlocked_skills = con.execute(
                "SELECT COUNT(*) c FROM skills WHERE unlocked_at IS NOT NULL"
            ).fetchone()["c"]
            boss_kills = con.execute(
                "SELECT COUNT(*) c FROM bosses WHERE status='defeated'"
            ).fetchone()["c"]
            titles = [r["reward_title"] for r in con.execute(
                "SELECT reward_title FROM achievements WHERE completed_at IS NOT NULL AND reward_title IS NOT NULL"
            ).fetchall()]

        # Attribute scores are intentionally not spendable points. They are a
        # transparent summary of real progression, so old saves and new saves
        # always produce the same result and no points can disappear.
        attribute_breakdown: list[dict[str, Any]] = []
        attributes: dict[str, int] = {}
        for role in roles:
            level = max(1, int(role["level"] or 1))
            meta = skill_meta.get(int(role["id"]), {"unlocked": 0, "mastered": 0})
            level_bonus = (level - 1) * 2
            skill_bonus = int(meta["unlocked"])
            mastery_bonus = int(meta["mastered"])
            score = 10 + level_bonus + skill_bonus + mastery_bonus
            name = str(role["attribute_name"] or "属性")
            attributes[name] = score
            attribute_breakdown.append({
                "name": name,
                "role_name": role["name"],
                "score": score,
                "base": 10,
                "level_bonus": level_bonus,
                "skill_bonus": skill_bonus,
                "mastery_bonus": mastery_bonus,
                "detail": f"基础 10 · 等级 +{level_bonus} · 技能 +{skill_bonus} · 精进 +{mastery_bonus}",
            })
        return {
            **player,
            "roles": roles,
            "class_name": character_class(highest["name"]),
            "dominant_role": highest["name"],
            "attributes": attributes,
            "attribute_breakdown": attribute_breakdown,
            "attribute_total": sum(attributes.values()),
            "unlocked_skills": int(unlocked_skills),
            "boss_kills": int(boss_kills),
            "titles": titles,
        }

    def equip_title(self, title: str) -> None:
        allowed = {"地球新手", *self.get_character_profile()["titles"]}
        if title not in allowed:
            raise ValueError("称号尚未解锁")
        with self.connect() as con:
            con.execute("UPDATE player SET title=? WHERE id=1", (title,))

    # ------------------------------------------------------------------
    # Bosses
    # ------------------------------------------------------------------
    def get_bosses(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT b.*, CASE WHEN p.active_boss_id=b.id THEN 1 ELSE 0 END is_active
                   FROM bosses b CROSS JOIN player p WHERE p.id=1 ORDER BY b.id"""
            ).fetchall()

    def get_active_boss(self) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute(
                "SELECT b.* FROM bosses b JOIN player p ON p.active_boss_id=b.id WHERE p.id=1"
            ).fetchone()

    def set_active_boss(self, boss_id: int) -> None:
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM bosses WHERE id=?", (boss_id,)).fetchone():
                raise ValueError("首领不存在")
            con.execute("UPDATE player SET active_boss_id=? WHERE id=1", (boss_id,))

    def reset_boss(self, boss_id: int) -> None:
        with self.connect() as con:
            boss = con.execute("SELECT * FROM bosses WHERE id=?", (boss_id,)).fetchone()
            if boss is None:
                raise ValueError("首领不存在")
            con.execute("UPDATE bosses SET hp=max_hp, status='active', defeated_at=NULL WHERE id=?", (boss_id,))
            con.execute("UPDATE player SET active_boss_id=? WHERE id=1", (boss_id,))
            self._add_event(con, "boss_awakened", "首领苏醒", f"{boss['name']}再次出现。")

    def heal_active_boss(self, amount: int, note: str = "手动记录失控行为") -> dict[str, Any] | None:
        with self.connect() as con:
            return self._apply_boss_delta(con, max(1, int(amount)), "setback", None, note)

    def get_boss_events(self, boss_id: int, limit: int = 8) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM boss_events WHERE boss_id=? ORDER BY id DESC LIMIT ?", (boss_id, int(limit))
            ).fetchall()

    # ------------------------------------------------------------------
    # Hidden quests, achievements, world and story
    # ------------------------------------------------------------------
    def _dopamine_silence_streak(self) -> int:
        with self.connect() as con:
            activity_rows = con.execute(
                """SELECT d FROM (
                     SELECT quest_date d FROM quests WHERE status='completed'
                     UNION SELECT entry_date d FROM time_entries
                   ) ORDER BY d DESC"""
            ).fetchall()
            bad_rows = con.execute(
                """SELECT DISTINCT entry_date d FROM time_entries
                   WHERE ownership_type='unowned' AND
                   (LOWER(category) LIKE '%short%' OR category LIKE '%短视频%' OR LOWER(category) LIKE '%video%')"""
            ).fetchall()
        active_dates = {date.fromisoformat(r["d"]) for r in activity_rows}
        bad_dates = {date.fromisoformat(r["d"]) for r in bad_rows}
        if not active_dates:
            return 0
        cursor = date.today()
        if cursor not in active_dates:
            cursor -= timedelta(days=1)
        streak = 0
        while cursor in active_dates and cursor not in bad_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def refresh_hidden_quests(self) -> list[str]:
        values = {"HIDDEN_STREAK": self.get_streak(), "HIDDEN_DOPAMINE": self._dopamine_silence_streak()}
        completed_titles: list[str] = []
        with self.connect() as con:
            for key, value in values.items():
                quest = con.execute("SELECT * FROM quests WHERE repeat_key=?", (key,)).fetchone()
                if quest is None:
                    continue
                complete_now = value >= int(quest["target_value"]) and quest["status"] == "pending"
                con.execute(
                    """UPDATE quests SET current_value=?, revealed=CASE WHEN ?>0 THEN 1 ELSE revealed END,
                       status=CASE WHEN ?>=target_value THEN 'completed' ELSE status END,
                       completed_at=CASE WHEN ?>=target_value AND completed_at IS NULL THEN ? ELSE completed_at END
                       WHERE id=?""",
                    (value, value, value, value, NOW(), quest["id"]),
                )
                if complete_now:
                    role = con.execute("SELECT name FROM roles WHERE id=?", (quest["role_id"],)).fetchone()
                    self._award_role_exp(con, quest["role_id"], quest["exp_reward"], quest["title"])
                    self._log_reward(
                        con, date.today().isoformat(), "hidden_quest", int(quest["id"]),
                        role["name"] if role else None, int(quest["exp_reward"]), 0,
                        f"隐藏任务：{quest['title']}",
                    )
                    completed_titles.append(quest["title"])
                    self._add_event(con, "hidden_quest", "隐藏任务完成", quest["title"])
        return completed_titles

    def get_achievements(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM achievements ORDER BY completed_at IS NULL, category, id").fetchall()

    def _ownership_days(self, threshold: int = 80) -> int:
        with self.connect() as con:
            rows = con.execute(
                """SELECT day, SUM(minutes) total,
                   SUM(CASE WHEN ownership='owned' THEN minutes ELSE 0 END) owned
                   FROM (
                       SELECT entry_date day, duration_minutes minutes, ownership_type ownership FROM time_entries
                       UNION ALL
                       SELECT record_date day, 30 minutes, ownership_type ownership
                       FROM half_hour_records WHERE category<>''
                       AND slot_index>=? AND slot_index<?
                   ) GROUP BY day""",
                (TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchall()
        return sum(1 for r in rows if r["total"] and round(r["owned"] / r["total"] * 100) >= threshold)

    def refresh_achievements(self) -> list[str]:
        today = date.today().isoformat()
        with self.connect() as con:
            values = {
                "FIRST_QUEST": con.execute("SELECT COUNT(*) c FROM quests WHERE status='completed'").fetchone()["c"],
                "THREE_IN_DAY": con.execute("SELECT COUNT(*) c FROM quests WHERE status='completed' AND quest_date=?", (today,)).fetchone()["c"],
                "RESEARCH_3_DAYS": con.execute("""SELECT COUNT(DISTINCT q.quest_date) c FROM quests q
                    JOIN roles r ON r.id=q.role_id WHERE q.status='completed' AND r.name='Scholar'""").fetchone()["c"],
                "EXERCISE_5": con.execute("""SELECT COUNT(*) c FROM quests q JOIN roles r ON r.id=q.role_id
                    WHERE q.status='completed' AND r.name='Athlete'""").fetchone()["c"],
                "EXP_500": con.execute("SELECT total_exp c FROM player WHERE id=1").fetchone()["c"],
                "STREAK_7": self.get_streak(),
                "LEVEL_5": con.execute("SELECT account_level c FROM player WHERE id=1").fetchone()["c"],
                "SKILL_5": con.execute("SELECT COUNT(*) c FROM skills WHERE unlocked_at IS NOT NULL").fetchone()["c"],
                "BOSS_1": con.execute("SELECT COUNT(*) c FROM bosses WHERE status='defeated'").fetchone()["c"],
                "OWNERSHIP_3": self._ownership_days(),
                "WORLD_25": con.execute("SELECT COALESCE(MAX(progress),0) c FROM world_regions").fetchone()["c"],
                "ALL_ROLES_3": con.execute("SELECT COALESCE(MIN(level),1) c FROM roles").fetchone()["c"],
                "FOCUS_CHAIN": self._max_focus_chain(con, today),
                "CHEST_8": self._action_count(con, today),
            }
            unlocked: list[str] = []
            for code, value in values.items():
                row = con.execute("SELECT * FROM achievements WHERE code=?", (code,)).fetchone()
                if row is None:
                    continue
                completed_at = row["completed_at"]
                if int(value) >= int(row["target_value"]) and completed_at is None:
                    completed_at = NOW()
                    unlocked.append(row["title"])
                    self._add_event(
                        con, "achievement", "成就解锁", row["title"],
                        {"title_reward": row["reward_title"]},
                    )
                con.execute(
                    "UPDATE achievements SET current_value=?, completed_at=? WHERE code=?",
                    (int(value), completed_at, code),
                )
        return unlocked

    def _metric_value(self, con: sqlite3.Connection, metric: str) -> int:
        if metric == "manual":
            return -1
        if metric == "scholar_quests":
            return int(con.execute("""SELECT COUNT(*) c FROM quests q JOIN roles r ON r.id=q.role_id
                WHERE q.status='completed' AND r.name='Scholar'""").fetchone()["c"])
        if metric == "athlete_quests":
            return int(con.execute("""SELECT COUNT(*) c FROM quests q JOIN roles r ON r.id=q.role_id
                WHERE q.status='completed' AND r.name='Athlete'""").fetchone()["c"])
        if metric == "streak":
            return self.get_streak()
        if metric == "ownership_days":
            return self._ownership_days()
        if metric == "main_progress":
            row = con.execute("SELECT COALESCE(MAX(progress),0) c FROM main_quests").fetchone()
            return int(row["c"])
        if metric.startswith("role:"):
            role = metric.split(":", 1)[1]
            row = con.execute("SELECT level FROM roles WHERE name=?", (role,)).fetchone()
            return int(row["level"]) if row else 0
        if metric.startswith("skill:"):
            code = metric.split(":", 1)[1]
            row = con.execute("SELECT level, unlocked_at FROM skills WHERE code=?", (code,)).fetchone()
            return int(row["level"]) if row and row["unlocked_at"] else 0
        if metric.startswith("boss:"):
            code = metric.split(":", 1)[1]
            row = con.execute("SELECT status FROM bosses WHERE code=?", (code,)).fetchone()
            return 1 if row and row["status"] == "defeated" else 0
        return 0

    def refresh_world_progress(self) -> None:
        with self.connect() as con:
            nodes = con.execute("SELECT * FROM world_nodes").fetchall()
            for node in nodes:
                value = self._metric_value(con, node["metric_key"])
                if value >= 0:
                    con.execute("UPDATE world_nodes SET current_value=? WHERE id=?", (value, node["id"]))
            regions = con.execute("SELECT * FROM world_regions ORDER BY sort_order").fetchall()
            previous_progress = 100
            for index, region in enumerate(regions):
                rows = con.execute("SELECT * FROM world_nodes WHERE region_id=?", (region["id"],)).fetchall()
                progress = round(sum(min(100, r["current_value"] / r["target_value"] * 100) for r in rows) / len(rows)) if rows else 0
                unlocked = 1 if index == 0 or previous_progress >= 25 else int(region["unlocked"])
                con.execute("UPDATE world_regions SET progress=?, unlocked=? WHERE id=?", (progress, unlocked, region["id"]))
                for row in rows:
                    status = "locked" if not unlocked else ("completed" if row["current_value"] >= row["target_value"] else "active")
                    con.execute("UPDATE world_nodes SET status=? WHERE id=?", (status, row["id"]))
                previous_progress = progress

    def get_world_map(self) -> list[dict[str, Any]]:
        self.refresh_world_progress()
        with self.connect() as con:
            regions = con.execute("SELECT * FROM world_regions ORDER BY sort_order").fetchall()
            result = []
            for region in regions:
                nodes = con.execute(
                    "SELECT * FROM world_nodes WHERE region_id=? ORDER BY sort_order", (region["id"],)
                ).fetchall()
                result.append({**dict(region), "nodes": [dict(n) for n in nodes]})
            return result

    def advance_world_node(self, node_id: int, amount: int = 1) -> None:
        with self.connect() as con:
            node = con.execute("SELECT * FROM world_nodes WHERE id=?", (node_id,)).fetchone()
            if node is None or node["metric_key"] != "manual":
                raise ValueError("该节点由游戏数据自动推进")
            con.execute(
                "UPDATE world_nodes SET current_value=MIN(target_value,current_value+?) WHERE id=?",
                (max(1, int(amount)), node_id),
            )
        self.refresh_world_progress()
        self.refresh_achievements()
        self.refresh_story_events()

    def refresh_story_events(self) -> list[str]:
        unlocked: list[str] = []
        with self.connect() as con:
            account_level = int(con.execute("SELECT account_level FROM player WHERE id=1").fetchone()["account_level"])
            metrics = {
                "account_level": account_level,
                "quest_count": int(con.execute("SELECT COUNT(*) c FROM quests WHERE status='completed'").fetchone()["c"]),
                "skill_unlocked": int(con.execute("SELECT COUNT(*) c FROM skills WHERE unlocked_at IS NOT NULL").fetchone()["c"]),
                "boss_defeated": int(con.execute("SELECT COUNT(*) c FROM bosses WHERE status='defeated'").fetchone()["c"]),
                "world_progress": int(con.execute("SELECT COALESCE(MAX(progress),0) c FROM world_regions").fetchone()["c"]),
            }
            for story in con.execute("SELECT * FROM story_events ORDER BY chapter, id").fetchall():
                if story["unlocked_at"] is None and metrics.get(story["trigger_type"], 0) >= story["trigger_value"]:
                    con.execute("UPDATE story_events SET unlocked_at=? WHERE id=?", (NOW(), story["id"]))
                    unlocked.append(story["title"])
                    self._add_event(con, "story", "剧情解锁", story["title"], {"chapter": story["chapter"]})
        return unlocked

    def get_story_events(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM story_events ORDER BY chapter, id").fetchall()

    def mark_story_seen(self, story_id: int) -> None:
        with self.connect() as con:
            con.execute("UPDATE story_events SET seen_at=COALESCE(seen_at,?) WHERE id=?", (NOW(), story_id))

    def _npc_is_unlocked(self, con: sqlite3.Connection, npc: sqlite3.Row) -> bool:
        if npc["unlock_type"] == "account_level":
            value = con.execute("SELECT account_level c FROM player WHERE id=1").fetchone()["c"]
        elif npc["unlock_type"] == "boss_defeated":
            value = con.execute("SELECT COUNT(*) c FROM bosses WHERE status='defeated'").fetchone()["c"]
        else:
            value = 0
        return int(value) >= int(npc["unlock_value"])

    def get_npcs(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [{**dict(npc), "unlocked": self._npc_is_unlocked(con, npc)} for npc in con.execute("SELECT * FROM npcs ORDER BY id")]

    def talk_to_npc(self, npc_id: int) -> dict[str, Any]:
        with self.connect() as con:
            npc = con.execute("SELECT * FROM npcs WHERE id=?", (npc_id,)).fetchone()
            if npc is None or not self._npc_is_unlocked(con, npc):
                raise ValueError("NPC 尚未解锁")
            today = date.today().isoformat()
            existing = con.execute(
                "SELECT dialogue FROM npc_interactions WHERE npc_id=? AND interaction_date=?", (npc_id, today)
            ).fetchone()
            if existing:
                return {"name": npc["name"], "dialogue": existing["dialogue"], "affinity": npc["affinity"], "new": False}
            profile = self.get_character_profile()
            if npc["code"] == "LYRA":
                dialogue = "不要整理整个知识体系。告诉我，下一次 25 分钟要回答哪个问题？" if profile["attributes"].get("智识", 1) < 5 else "你的阅读已经足够形成判断。今天写下一个可被反驳的结论。"
            elif npc["code"] == "ATLAS":
                dialogue = "最小的训练也算训练。先穿鞋，身体会替意志完成下一步。" if profile["attributes"].get("活力", 1) < 5 else "负荷之后要留下恢复空间。长期战役不奖励透支。"
            else:
                dialogue = "Boss 回血不是失败，只是模式再次出现。记录触发点，然后发动一次小攻击。"
            affinity = min(100, int(npc["affinity"]) + 1)
            con.execute("UPDATE npcs SET affinity=? WHERE id=?", (affinity, npc_id))
            con.execute(
                "INSERT INTO npc_interactions(npc_id, interaction_date, dialogue, created_at) VALUES(?, ?, ?, ?)",
                (npc_id, today, dialogue, NOW()),
            )
            return {"name": npc["name"], "dialogue": dialogue, "affinity": affinity, "new": True}

    # ------------------------------------------------------------------
    # Dashboard, events and maintenance
    # ------------------------------------------------------------------
    def get_recent_events(self, limit: int = 8) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM game_events ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        return {
            "player": dict(self.get_player()), "roles": [dict(r) for r in self.get_roles()],
            "quests": [dict(q) for q in self.get_today_quests()], "summary": self.get_today_summary(),
            "boss": dict(self.get_active_boss()) if self.get_active_boss() else None,
            "main_quest": dict(self.get_main_quest()) if self.get_main_quest() else None,
            "events": [dict(e) for e in self.get_recent_events(5)],
        }

    def update_main_quest_progress(self, progress: int) -> None:
        value = max(0, min(100, int(progress)))
        with self.connect() as con:
            con.execute(
                """UPDATE main_quests SET progress=?, status=CASE WHEN ?>=100 THEN 'completed' ELSE 'active' END
                   WHERE id=(SELECT id FROM main_quests WHERE active=1 ORDER BY id LIMIT 1)""",
                (value, value),
            )
            self._claim_completed_main_quests(con)
        self.refresh_world_progress()
        self.refresh_story_events()

    def refresh_all_progression(self) -> None:
        with self.connect() as con:
            for role in con.execute("SELECT * FROM roles").fetchall():
                self._unlock_eligible_skills(con, role["id"])
        self.refresh_hidden_quests()
        self.refresh_world_progress()
        self.refresh_achievements()
        self.refresh_story_events()

    def backup(self, destination_dir: Path, keep: int = 14) -> Path | None:
        if not self.path.exists():
            return None
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"earth_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        self.export_database(destination)
        for old in sorted(destination_dir.glob("earth_*.db"), reverse=True)[keep:]:
            old.unlink(missing_ok=True)
        return destination

    def export_database(self, destination: Path) -> Path:
        """Create a consistent SQLite snapshot, including any WAL changes."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self.path.resolve():
            raise ValueError("导出路径不能与当前存档相同")
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return destination

    @staticmethod
    def validate_database_file(source: Path) -> None:
        source = Path(source)
        if not source.exists() or not source.is_file():
            raise ValueError("所选存档文件不存在")
        try:
            with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as con:
                tables = {row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
        except sqlite3.DatabaseError as exc:
            raise ValueError("所选文件不是有效的 SQLite 存档") from exc
        required = {"player", "roles", "quests"}
        if not required.issubset(tables):
            raise ValueError("所选文件不是 Earth Online 存档")

    def import_database(self, source: Path, backup_dir: Path | None = None) -> None:
        """Replace the current save after validation and an optional backup."""
        source = Path(source)
        self.validate_database_file(source)
        if source.resolve() == self.path.resolve():
            return
        if backup_dir is not None and self.path.exists():
            self.backup(Path(backup_dir), keep=20)
        temporary = self.path.with_suffix(".importing.db")
        shutil.copy2(source, temporary)
        temporary.replace(self.path)
        self.initialize()

# v2.2 additive recovery/action layer.
from database.v22 import install_v22 as _install_v22
_install_v22(Database)

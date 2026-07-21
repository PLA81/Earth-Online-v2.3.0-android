from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from system.game_rules import role_for_text, skill_code_for_action
from system.localization import role_display
from system.time_window import TRACKING_END_SLOT, TRACKING_SLOT_COUNT, TRACKING_START_SLOT

NOW = lambda: datetime.now().isoformat(timespec="seconds")

DAY_MODE_NAMES = {
    "survival": "生存日",
    "normal": "正常日",
    "adventure": "冒险日",
}
TIME_STATUS_NAMES = {
    "planned_done": "按计划完成",
    "intentional_change": "主动调整",
    "unowned": "无意识失控",
    "unrecorded": "未记录",
}
TIER_NAMES = {
    "minimum": "最低版",
    "standard": "标准版",
    "challenge": "挑战版",
    "recovery": "恢复行动",
    "environment": "环境行动",
}


def _default_tiers(title: str, role_name: str) -> tuple[str, str, str]:
    lowered = title.casefold()
    if role_name == "Scholar":
        return (
            "打开材料，写下下一步并推进 5 分钟",
            "完成一个 25–45 分钟工作块",
            "完成两个工作块并留下可复用的科研产物",
        )
    if role_name == "Athlete":
        return (
            "换好衣服，步行或热身 5 分钟",
            "完成计划中的基础训练",
            "完成训练、整理恢复并记录关键数据",
        )
    if role_name == "Bard":
        return (
            "拿起乐器，练习一个动作或小节 2 分钟",
            "完成 15–20 分钟结构化练习",
            "完成技术、曲目并留下短录音或作品",
        )
    if role_name == "Guardian" or any(word in lowered for word in ("手机", "短视频", "专注")):
        return (
            "把手机放远或保护环境 10 分钟",
            "完成一个无手机工作块",
            "完成一个关键无手机窗口并记录环境机制",
        )
    return (
        "做一个不超过 5 分钟的最小动作",
        "完成一个标准行动块",
        "完成标准行动并留下产物与明确下一步",
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def install_v22(Database: type) -> None:
    """Install the v2.2 recovery/action layer without rewriting the v2.1 engine.

    The extension is deliberately additive. Existing databases are migrated in
    place, and original methods remain available through captured references.
    """

    original_initialize = Database.initialize
    original_add_quest = Database.add_quest
    original_get_today_quests = Database.get_today_quests
    original_ensure_daily_quests = Database.ensure_daily_quests
    original_get_streak = Database.get_streak
    original_get_quests_by_type = Database.get_quests_by_type
    original_refresh_achievements = Database.refresh_achievements

    def _migrate_v22(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS real_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    role_name TEXT,
                    category TEXT NOT NULL DEFAULT '',
                    quest_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'started',
                    tier TEXT NOT NULL DEFAULT 'minimum',
                    intended_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    launch_delay_minutes INTEGER NOT NULL DEFAULT 0,
                    output_type TEXT NOT NULL DEFAULT '',
                    output_text TEXT NOT NULL DEFAULT '',
                    next_step TEXT NOT NULL DEFAULT '',
                    help_sought INTEGER NOT NULL DEFAULT 0,
                    quality_cycle INTEGER NOT NULL DEFAULT 0,
                    core_exp INTEGER NOT NULL DEFAULT 0,
                    bonus_exp INTEGER NOT NULL DEFAULT 0,
                    gold INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_checkins (
                    checkin_date TEXT PRIMARY KEY,
                    day_mode TEXT NOT NULL DEFAULT 'normal',
                    energy INTEGER NOT NULL DEFAULT 3,
                    mood INTEGER NOT NULL DEFAULT 3,
                    sleep_recovery INTEGER NOT NULL DEFAULT 3,
                    bedtime TEXT NOT NULL DEFAULT '',
                    wake_time TEXT NOT NULL DEFAULT '',
                    night_phone INTEGER NOT NULL DEFAULT 0,
                    daytime_sleepy INTEGER NOT NULL DEFAULT 0,
                    meals INTEGER NOT NULL DEFAULT 0,
                    protein INTEGER NOT NULL DEFAULT 0,
                    produce INTEGER NOT NULL DEFAULT 0,
                    water INTEGER NOT NULL DEFAULT 0,
                    evening_output TEXT NOT NULL DEFAULT '',
                    evening_trigger TEXT NOT NULL DEFAULT '',
                    next_physical_action TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS incident_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_date TEXT NOT NULL,
                    slot_index INTEGER,
                    trigger_environment TEXT NOT NULL DEFAULT '',
                    trigger_emotion TEXT NOT NULL DEFAULT '',
                    application TEXT NOT NULL DEFAULT '',
                    duration_minutes INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    stopped_at TEXT,
                    recovered_at TEXT,
                    recovery_action TEXT NOT NULL DEFAULT '',
                    next_step TEXT NOT NULL DEFAULT '',
                    recovery_delay_minutes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS phone_environment (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    parking_location TEXT NOT NULL DEFAULT '',
                    bedtime_charge_location TEXT NOT NULL DEFAULT '',
                    focus_rule TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS growth_days (
                    growth_date TEXT PRIMARY KEY,
                    day_class TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    protected INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS weekly_reviews (
                    week_end TEXT PRIMARY KEY,
                    helped TEXT NOT NULL DEFAULT '',
                    repeated_failure TEXT NOT NULL DEFAULT '',
                    next_experiment TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS seasons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    primary_goals TEXT NOT NULL DEFAULT '',
                    maintenance_goals TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS athlete_profile (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    height_cm REAL,
                    weight_kg REAL,
                    standing_reach_cm REAL,
                    standing_jump_cm REAL,
                    approach_jump_cm REAL,
                    time_30m REAL,
                    time_100m REAL,
                    time_200m REAL,
                    time_300m REAL,
                    time_400m REAL,
                    strength_baseline TEXT NOT NULL DEFAULT '',
                    pain_location TEXT NOT NULL DEFAULT '',
                    pain_score INTEGER NOT NULL DEFAULT 0,
                    fatigue INTEGER NOT NULL DEFAULT 3,
                    recovery INTEGER NOT NULL DEFAULT 3,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guitar_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT NOT NULL,
                    technique TEXT NOT NULL DEFAULT '',
                    repertoire TEXT NOT NULL DEFAULT '',
                    ear_theory TEXT NOT NULL DEFAULT '',
                    expression TEXT NOT NULL DEFAULT '',
                    recording_path TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_real_actions_date ON real_actions(action_date, status);
                CREATE INDEX IF NOT EXISTS idx_real_actions_quest ON real_actions(quest_id);
                CREATE INDEX IF NOT EXISTS idx_incident_date ON incident_reports(incident_date);
                CREATE INDEX IF NOT EXISTS idx_growth_date ON growth_days(growth_date);
                """
            )
            for table, name, declaration in (
                ("quests", "real_action_id", "INTEGER"),
                ("quests", "minimum_text", "TEXT NOT NULL DEFAULT ''"),
                ("quests", "standard_text", "TEXT NOT NULL DEFAULT ''"),
                ("quests", "challenge_text", "TEXT NOT NULL DEFAULT ''"),
                ("quest_templates", "minimum_text", "TEXT NOT NULL DEFAULT ''"),
                ("quest_templates", "standard_text", "TEXT NOT NULL DEFAULT ''"),
                ("quest_templates", "challenge_text", "TEXT NOT NULL DEFAULT ''"),
                ("time_entries", "real_action_id", "INTEGER"),
                ("half_hour_records", "real_action_id", "INTEGER"),
                ("half_hour_records", "planned_category", "TEXT NOT NULL DEFAULT ''"),
                ("half_hour_records", "time_status", "TEXT NOT NULL DEFAULT 'planned_done'"),
                ("half_hour_records", "incident_id", "INTEGER"),
                ("reward_ledger", "real_action_id", "INTEGER"),
            ):
                self._ensure_column(con, table, name, declaration)
            con.execute(
                "INSERT OR IGNORE INTO phone_environment(id, updated_at) VALUES(1, ?)",
                (NOW(),),
            )
            con.execute(
                "INSERT OR IGNORE INTO athlete_profile(id, updated_at) VALUES(1, ?)",
                (NOW(),),
            )
            today = date.today()
            con.execute(
                """INSERT INTO seasons(title, start_date, end_date, primary_goals, maintenance_goals, status, created_at)
                   SELECT '第一个十二周赛季', ?, ?,
                          '恢复稳定科研启动能力\n稳定睡眠并减少手机失控',
                          '每周基础力量与跑步\n每天或隔天吉他十分钟\n保证饮食基本规律',
                          'active', ?
                   WHERE NOT EXISTS(SELECT 1 FROM seasons WHERE status='active')""",
                (today.isoformat(), (today + timedelta(weeks=12) - timedelta(days=1)).isoformat(), NOW()),
            )
            # Migrate old owned/unowned records into the richer time status model.
            con.execute(
                """UPDATE half_hour_records SET time_status=
                       CASE WHEN ownership_type='unowned' THEN 'unowned'
                            WHEN time_status='' OR time_status IS NULL THEN 'planned_done'
                            ELSE time_status END"""
            )
            # Research skill tree: stable codes, more meaningful names.
            skill_updates = {
                "scholar_literature": ("文献解码", "重建问题、假设、关键推导与适用边界。"),
                "scholar_mathematics": ("数学锻造", "形成完整推导、可复用公式与明确卡点。"),
                "scholar_python": ("计算实验", "用代码、极限情况、维度分析和测试验证想法。"),
                "scholar_writing": ("科研写作", "把笔记转化为结构清晰且可检验的论证。"),
                "scholar_deep_work": ("学术沟通", "及时暴露问题、汇报进度并主动寻求帮助。"),
                "guardian_focus": ("启动工程", "缩短从决定到真正开始之间的距离。"),
                "guardian_digital": ("环境工程", "通过手机停泊点和低干扰环境减少意志消耗。"),
                "guardian_command": ("恢复能力", "失控以后停止下滑，并重新开始一个小动作。"),
            }
            for code, (name, desc) in skill_updates.items():
                con.execute("UPDATE skills SET name=?, description=? WHERE code=?", (name, desc, code))
            # Provide tier text for every template and existing quest.
            role_map = {r["id"]: r["name"] for r in con.execute("SELECT id,name FROM roles")}
            role_ids = {name: role_id for role_id, name in role_map.items()}
            for table in ("quest_templates", "quests"):
                rows = con.execute(
                    f"SELECT id,title,role_id,minimum_text,standard_text,challenge_text FROM {table}"
                ).fetchall()
                for row in rows:
                    minimum, standard, challenge = _default_tiers(row["title"], role_map.get(row["role_id"], "Mind"))
                    con.execute(
                        f"""UPDATE {table} SET minimum_text=CASE WHEN minimum_text='' THEN ? ELSE minimum_text END,
                           standard_text=CASE WHEN standard_text='' THEN ? ELSE standard_text END,
                           challenge_text=CASE WHEN challenge_text='' THEN ? ELSE challenge_text END WHERE id=?""",
                        (minimum, standard, challenge, row["id"]),
                    )
            # The default day now exposes only three deliberate choices:
            # research, body, and recovery/music. User-created daily tasks remain.
            con.execute("UPDATE quest_templates SET enabled=0")
            core_templates = (
                ("今日科研主线", "Scholar", 10),
                ("今日身体行动", "Athlete", 10),
                ("今日恢复或音乐", "Mind", 10),
            )
            legacy_default_titles = (
                "科研 25 分钟", "阅读 10 页", "吉他 10 分钟", "运动一次", "睡前不用手机",
            )
            placeholders = ",".join("?" for _ in legacy_default_titles)
            con.execute(
                f"""UPDATE quests SET status='deleted'
                    WHERE status='pending' AND quest_type='daily' AND real_action_id IS NULL
                    AND title IN ({placeholders})""",
                legacy_default_titles,
            )
            for title, role_name, reward in core_templates:
                role_id = role_ids[role_name]
                row = con.execute("SELECT id FROM quest_templates WHERE title=?", (title,)).fetchone()
                if row:
                    con.execute(
                        "UPDATE quest_templates SET role_id=?,exp_reward=?,enabled=1 WHERE id=?",
                        (role_id, reward, row["id"]),
                    )
                else:
                    con.execute(
                        "INSERT INTO quest_templates(title,role_id,exp_reward,enabled) VALUES(?,?,?,1)",
                        (title, role_id, reward),
                    )
                minimum, standard, challenge = _default_tiers(title, role_name)
                con.execute(
                    """UPDATE quest_templates SET minimum_text=?,standard_text=?,challenge_text=?
                       WHERE title=?""",
                    (minimum, standard, challenge, title),
                )
            # New recovery/output achievements. Old achievements remain historical.
            achievements = (
                ("RECOVERY_10", "重新开始十次", "在失控或低谷之后完成十次恢复协议。", 10, "恢复", "归航者", 0),
                ("OUTPUT_10", "十件现实产物", "累计留下十件可检查的现实产物。", 10, "产物", "作品锻造者", 0),
                ("START_DELAY_5", "五分钟启动", "累计十次在五分钟内开始现实行动。", 10, "启动", "迅捷启动者", 0),
                ("QUALITY_CYCLE_5", "离开并回来", "完成五次高质量工作—休息—返回循环。", 5, "专注", "节律守护者", 0),
            )
            for row in achievements:
                con.execute(
                    """INSERT INTO achievements(code,title,description,target_value,category,reward_title,hidden)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET
                       title=excluded.title, description=excluded.description,
                       target_value=excluded.target_value, category=excluded.category,
                       reward_title=excluded.reward_title""",
                    row,
                )
            # Preserve historical continuity when upgrading from v2.1: a day
            # with at least one completed quest becomes a historical full day.
            # No new EXP is awarded during this backfill.
            con.execute(
                """INSERT OR IGNORE INTO growth_days(growth_date,day_class,source,protected,created_at)
                   SELECT quest_date,'full','旧版任务历史',0,COALESCE(MIN(completed_at),MIN(created_at),?)
                   FROM quests
                   WHERE status='completed' AND quest_date IS NOT NULL AND quest_date<>''
                   GROUP BY quest_date""",
                (NOW(),),
            )
            # Existing completed quests are linked to one historical reality
            # action so future reports do not count task/time/output separately.
            legacy_rows = con.execute(
                """SELECT q.*,r.name role_name FROM quests q JOIN roles r ON r.id=q.role_id
                   WHERE q.status='completed' AND q.real_action_id IS NULL"""
            ).fetchall()
            for quest in legacy_rows:
                completed_at = quest["completed_at"] or quest["created_at"] or NOW()
                action_id = self._create_action(
                    con, title=quest["title"], role_name=quest["role_name"], category=quest["title"],
                    quest_id=int(quest["id"]), action_date=quest["quest_date"] or str(completed_at)[:10],
                    status="completed", tier="standard", started_at=completed_at,
                )
                con.execute(
                    """UPDATE real_actions SET completed_at=?,core_exp=?,updated_at=? WHERE id=?""",
                    (completed_at, max(0, int(quest["exp_reward"] or 0)), NOW(), action_id),
                )
                con.execute("UPDATE quests SET real_action_id=? WHERE id=?", (action_id, quest["id"]))
            con.execute(
                "INSERT OR REPLACE INTO app_settings(key,value) VALUES('schema_version','2.3.0')"
            )

    def initialize(self) -> None:
        original_initialize(self)
        _migrate_v22(self)
        self.ensure_daily_quests()
        self._protect_previous_day()
        self._evaluate_growth_day(date.today())

    def ensure_daily_quests(self, day: date | None = None) -> None:
        day = day or date.today()
        key = day.isoformat()
        with self.connect() as con:
            try:
                templates = con.execute(
                    "SELECT title,role_id,exp_reward,minimum_text,standard_text,challenge_text FROM quest_templates WHERE enabled=1 ORDER BY id"
                ).fetchall()
            except sqlite3.OperationalError:
                # During original_initialize() the additive v2.2 columns do not
                # exist yet. Let the v2.1 method seed its legacy defaults; the
                # v2.2 migration then replaces them with the three core choices.
                return original_ensure_daily_quests(self, day)
            existing_titles = {
                row["title"] for row in con.execute(
                    "SELECT title FROM quests WHERE quest_date=? AND quest_type='daily' AND status!='deleted'", (key,)
                ).fetchall()
            }
            for template in templates:
                if template["title"] in existing_titles:
                    continue
                con.execute(
                    """INSERT INTO quests(title,quest_type,role_id,exp_reward,quest_date,created_at,
                       minimum_text,standard_text,challenge_text)
                       VALUES(?,'daily',?,?,?,?,?,?,?)""",
                    (template["title"], template["role_id"], template["exp_reward"], key, NOW(),
                     template["minimum_text"], template["standard_text"], template["challenge_text"]),
                )

    def add_quest(
        self,
        title: str,
        role_id: int,
        exp_reward: int,
        quest_type: str = "daily",
        target_value: int = 1,
        story_text: str = "",
        hidden: bool = False,
        minimum_text: str = "",
        standard_text: str = "",
        challenge_text: str = "",
    ) -> int:
        quest_id = original_add_quest(
            self, title, role_id, exp_reward, quest_type, target_value, story_text, hidden
        )
        with self.connect() as con:
            role = con.execute("SELECT name FROM roles WHERE id=?", (role_id,)).fetchone()
            defaults = _default_tiers(title, role["name"] if role else "Mind")
            con.execute(
                """UPDATE quests SET minimum_text=?, standard_text=?, challenge_text=? WHERE id=?""",
                (
                    minimum_text.strip() or defaults[0],
                    standard_text.strip() or defaults[1],
                    challenge_text.strip() or defaults[2],
                    quest_id,
                ),
            )
        return quest_id

    def _row_with_role(self, con, quest_id: int):
        return con.execute(
            """SELECT q.*, r.name role_name FROM quests q JOIN roles r ON r.id=q.role_id
               WHERE q.id=?""",
            (quest_id,),
        ).fetchone()

    def _create_action(
        self,
        con,
        *,
        title: str,
        role_name: str | None,
        category: str = "",
        quest_id: int | None = None,
        action_date: str | None = None,
        status: str = "started",
        tier: str = "minimum",
        started_at: str | None = None,
    ) -> int:
        now = NOW()
        cur = con.execute(
            """INSERT INTO real_actions(
                   action_date,title,role_name,category,quest_id,status,tier,intended_at,started_at,
                   created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                action_date or date.today().isoformat(), title[:160], role_name, category[:60], quest_id,
                status, tier, now, started_at or (now if status in {"started", "completed"} else None), now, now,
            ),
        )
        return int(cur.lastrowid)

    def _role_exp_used(self, con, action_date: str, role_name: str) -> int:
        row = con.execute(
            """SELECT COALESCE(SUM(core_exp+bonus_exp),0) value FROM real_actions
               WHERE action_date=? AND role_name=? AND tier NOT IN ('recovery','environment')""",
            (action_date, role_name),
        ).fetchone()
        return int(row["value"] or 0)

    def _calculate_action_exp(
        self,
        con,
        *,
        action_date: str,
        role_name: str,
        tier: str,
        has_output: bool,
        help_sought: bool,
        exempt_cap: bool = False,
    ) -> tuple[int, int, float]:
        # After the player's chosen bedtime, research can still be recorded but
        # does not create another optimisation loop or late-night reward chase.
        if role_name == "Scholar" and action_date == date.today().isoformat():
            checkin = con.execute(
                "SELECT bedtime FROM daily_checkins WHERE checkin_date=?", (action_date,)
            ).fetchone()
            bedtime = str(checkin["bedtime"] or "") if checkin else ""
            now_hm = datetime.now().strftime("%H:%M")
            if bedtime >= "18:00" and now_hm >= bedtime:
                return 0, 0, 1.0
        base = {"minimum": 5, "standard": 10, "challenge": 15, "recovery": 15, "environment": 10}.get(tier, 5)
        bonus = (10 if has_output else 0) + (10 if help_sought else 0)
        if tier in {"recovery", "environment"}:
            return base, bonus, 1.0
        count = int(con.execute(
            """SELECT COUNT(*) c FROM real_actions WHERE action_date=? AND role_name=?
               AND status='completed' AND tier NOT IN ('recovery','environment')""",
            (action_date, role_name),
        ).fetchone()["c"] or 0)
        multiplier = (1.0, 1.0, 0.75, 0.5, 0.25)[min(count, 4)]
        core = max(1, round(base * multiplier))
        bonus_awarded = round(bonus * multiplier)
        if exempt_cap:
            return core, bonus_awarded, multiplier
        available = max(0, 120 - self._role_exp_used(con, action_date, role_name))
        total = min(available, core + bonus_awarded)
        return min(core, total), max(0, total - min(core, total)), multiplier

    def _award_action(
        self,
        con,
        *,
        action_id: int,
        role_name: str,
        title: str,
        tier: str,
        output_text: str = "",
        help_sought: bool = False,
        quality_cycle: bool = False,
        recovery: bool = False,
    ) -> dict[str, Any]:
        action = con.execute("SELECT * FROM real_actions WHERE id=?", (action_id,)).fetchone()
        if action is None:
            raise ValueError("现实行动不存在")
        if int(action["core_exp"] or 0) + int(action["bonus_exp"] or 0) > 0:
            return {"reward": 0, "role_name": role_name, "already_rewarded": True}
        core, bonus, multiplier = self._calculate_action_exp(
            con,
            action_date=action["action_date"],
            role_name=role_name,
            tier=tier,
            has_output=bool(output_text.strip()),
            help_sought=help_sought,
            exempt_cap=recovery,
        )
        reward = core + bonus
        progression: dict[str, Any] = {}
        if reward:
            role = con.execute("SELECT * FROM roles WHERE name=?", (role_name,)).fetchone()
            if role:
                progression = self._award_role_exp(con, role["id"], reward, f"{title} {output_text}")
        gold = max(0, reward // 2)
        con.execute("UPDATE player SET gold=gold+? WHERE id=1", (gold,))
        con.execute(
            """UPDATE real_actions SET core_exp=?, bonus_exp=?, gold=?, quality_cycle=?, updated_at=? WHERE id=?""",
            (core, bonus, gold, int(quality_cycle), NOW(), action_id),
        )
        self._log_reward(
            con, action["action_date"], "real_action", action_id, role_name, reward, gold, title
        )
        con.execute(
            "UPDATE reward_ledger SET real_action_id=? WHERE source_type='real_action' AND source_id=?",
            (action_id, action_id),
        )
        damage = max(3, min(18, 3 + reward // 2)) if reward else 0
        boss = self._apply_boss_delta(con, -damage, "real_action", action_id, title) if damage else None
        self._add_event(
            con,
            "real_action_complete",
            "现实行动完成",
            f"{title} · {TIER_NAMES.get(tier, tier)} · {role_display(role_name)} +{reward} 经验",
            {"real_action_id": action_id, "tier": tier, "reward": reward, "multiplier": multiplier},
        )
        return {"reward": reward, "role_name": role_name, "boss": boss, "multiplier": multiplier, **progression}

    def start_quest_action(self, quest_id: int, launch_delay_minutes: int = 0) -> dict[str, Any]:
        with self.connect() as con:
            quest = self._row_with_role(con, quest_id)
            if quest is None:
                raise ValueError("任务不存在")
            existing = None
            if quest["real_action_id"]:
                existing = con.execute("SELECT * FROM real_actions WHERE id=?", (quest["real_action_id"],)).fetchone()
            if existing and existing["status"] in {"started", "completed"}:
                return {
                    "already_started": True,
                    "real_action_id": existing["id"],
                    "quest_title": quest["title"],
                    "role_name": quest["role_name"],
                }
            action_id = self._create_action(
                con, title=quest["title"], role_name=quest["role_name"], category=quest["title"],
                quest_id=quest_id, status="started", tier="minimum"
            )
            con.execute(
                "UPDATE quests SET real_action_id=? WHERE id=?",
                (action_id, quest_id),
            )
            con.execute(
                "UPDATE real_actions SET launch_delay_minutes=? WHERE id=?",
                (max(0, int(launch_delay_minutes)), action_id),
            )
            start_reward = 10
            if quest["role_name"] == "Scholar":
                checkin = con.execute(
                    "SELECT bedtime FROM daily_checkins WHERE checkin_date=?", (date.today().isoformat(),)
                ).fetchone()
                bedtime = str(checkin["bedtime"] or "") if checkin else ""
                if bedtime >= "18:00" and datetime.now().strftime("%H:%M") >= bedtime:
                    start_reward = 0
            role = con.execute("SELECT * FROM roles WHERE name=?", (quest["role_name"],)).fetchone()
            progression = self._award_role_exp(con, role["id"], start_reward, f"启动 {quest['title']}") if role and start_reward else {}
            if start_reward:
                self._log_reward(
                    con, date.today().isoformat(), "action_start", action_id, quest["role_name"], start_reward, 0,
                    f"启动：{quest['title']}"
                )
                con.execute(
                    "UPDATE reward_ledger SET real_action_id=? WHERE source_type='action_start' AND source_id=?",
                    (action_id, action_id),
                )
            boss = self._apply_boss_delta(con, -3, "action_start", action_id, f"启动：{quest['title']}") if start_reward else None
            self._add_event(
                con, "action_start", "已经开始",
                f"{quest['title']} · " + (f"启动奖励 +{start_reward} 经验" if start_reward else "已过睡前截止时间，仅记录不发放科研奖励"),
                {"real_action_id": action_id, "quest_id": quest_id},
            )
        self._evaluate_growth_day(date.today())
        return {
            "started": True, "real_action_id": action_id, "quest_title": quest["title"],
            "role_name": quest["role_name"], "reward": start_reward, "boss": boss, **progression,
        }

    def complete_quest(self, quest_id: int, action_data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = action_data or {}
        tier = str(data.get("tier") or "standard")
        if tier not in {"minimum", "standard", "challenge"}:
            tier = "standard"
        output_type = str(data.get("output_type") or "").strip()[:60]
        output_text = str(data.get("output_text") or "").strip()[:1000]
        next_step = str(data.get("next_step") or "").strip()[:500]
        help_sought = bool(data.get("help_sought"))
        quality_cycle = bool(data.get("quality_cycle"))
        launch_delay = max(0, _safe_int(data.get("launch_delay_minutes"), 0))
        if tier == "challenge" and not output_text:
            raise ValueError("挑战版需要留下一个可检查的现实产物或失败记录")
        with self.connect() as con:
            quest = self._row_with_role(con, quest_id)
            if quest is None:
                raise ValueError("任务不存在")
            if quest["status"] != "pending":
                return {"already_completed": True}
            action = None
            if quest["real_action_id"]:
                action = con.execute("SELECT * FROM real_actions WHERE id=?", (quest["real_action_id"],)).fetchone()
            if action is None:
                action_id = self._create_action(
                    con, title=quest["title"], role_name=quest["role_name"], category=quest["title"],
                    quest_id=quest_id, status="completed", tier=tier
                )
            else:
                action_id = int(action["id"])
            con.execute(
                """UPDATE real_actions SET status='completed', tier=?, completed_at=?,
                   launch_delay_minutes=?, output_type=?, output_text=?, next_step=?, help_sought=?,
                   quality_cycle=?, updated_at=? WHERE id=?""",
                (tier, NOW(), launch_delay, output_type, output_text, next_step, int(help_sought),
                 int(quality_cycle), NOW(), action_id),
            )
            con.execute(
                """UPDATE quests SET status='completed', current_value=target_value,
                   completed_at=?, real_action_id=? WHERE id=?""",
                (NOW(), action_id, quest_id),
            )
            reward_result = self._award_action(
                con, action_id=action_id, role_name=quest["role_name"], title=quest["title"],
                tier=tier, output_text=output_text, help_sought=help_sought,
                quality_cycle=quality_cycle,
            )
            if quest["role_name"] == "Scholar":
                progress = 1 + (2 if output_text else 0) + (1 if tier == "challenge" else 0)
                con.execute(
                    """UPDATE main_quests SET progress=MIN(100,progress+?),
                       status=CASE WHEN progress+?>=100 THEN 'completed' ELSE status END
                       WHERE active=1 AND status='active'""",
                    (progress, progress),
                )
            main_completed = self._claim_completed_main_quests(con)
        self._evaluate_growth_day(date.today())
        positive = self._process_positive_rewards(date.today())
        hidden = self.refresh_hidden_quests()
        achievements = self.refresh_achievements()
        self.refresh_world_progress()
        story = self.refresh_story_events()
        return {
            "already_completed": False,
            "quest_title": quest["title"],
            "real_action_id": action_id,
            "tier": tier,
            "output_text": output_text,
            "main_completed": main_completed,
            "hidden_completed": hidden,
            "unlocked_achievements": achievements,
            "unlocked_story": story,
            "positive_rewards": positive,
            **reward_result,
        }

    def _find_or_create_slot_action(
        self, con, key: str, slot: int, category: str, note: str, real_action_id: int | None
    ) -> tuple[int, dict[str, Any]]:
        if real_action_id:
            row = con.execute("SELECT * FROM real_actions WHERE id=?", (real_action_id,)).fetchone()
            if row:
                return int(row["id"]), {"reward": 0, "role_name": row["role_name"], "linked": True}
        inferred_role = role_for_text(category) or "Mind"
        active = con.execute(
            """SELECT * FROM real_actions WHERE action_date=? AND status='started'
               AND (role_name=? OR category=? OR title=?) ORDER BY id DESC LIMIT 1""",
            (key, inferred_role, category, category),
        ).fetchone()
        if active:
            return int(active["id"]), {"reward": 0, "role_name": active["role_name"], "linked": True}
        previous = con.execute(
            """SELECT h.real_action_id, h.category, h.time_status FROM half_hour_records h
               WHERE h.record_date=? AND h.slot_index=?""",
            (key, slot - 1),
        ).fetchone() if slot > TRACKING_START_SLOT else None
        if previous and previous["real_action_id"] and previous["category"].strip().casefold() == category.casefold() \
                and previous["time_status"] in {"planned_done", "intentional_change"}:
            return int(previous["real_action_id"]), {"reward": 0, "role_name": role_for_text(category), "linked": True}
        role_name = inferred_role
        action_id = self._create_action(
            con, title=category, role_name=role_name, category=category, action_date=key,
            status="completed", tier="minimum"
        )
        con.execute(
            """UPDATE real_actions SET completed_at=?, output_type=?, output_text=?, updated_at=? WHERE id=?""",
            (NOW(), "半小时记录" if note else "", note[:1000], NOW(), action_id),
        )
        reward = self._award_action(
            con, action_id=action_id, role_name=role_name, title=category, tier="minimum",
            output_text=note, help_sought=False, quality_cycle=False,
        )
        return action_id, reward

    def _insert_incident(
        self,
        con,
        *,
        trigger_environment: str = "",
        trigger_emotion: str = "",
        application: str = "",
        duration_minutes: int = 0,
        note: str = "",
        day: date | None = None,
        slot_index: int | None = None,
    ) -> int:
        day = day or date.today()
        cur = con.execute(
            """INSERT INTO incident_reports(
               incident_date,slot_index,trigger_environment,trigger_emotion,application,
               duration_minutes,note,stopped_at,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (day.isoformat(), slot_index, trigger_environment[:100], trigger_emotion[:100],
             application[:100], max(0, int(duration_minutes)), note[:500], NOW(), NOW()),
        )
        incident_id = int(cur.lastrowid)
        self._add_event(
            con, "incident_report", "敌情报告已保存",
            f"{application or '失控模式'} · {duration_minutes} 分钟 · 不扣经验、不让首领回血",
            {"incident_id": incident_id},
        )
        return incident_id

    def log_incident(
        self,
        trigger_environment: str = "",
        trigger_emotion: str = "",
        application: str = "",
        duration_minutes: int = 0,
        note: str = "",
        day: date | None = None,
        slot_index: int | None = None,
    ) -> int:
        with self.connect() as con:
            return self._insert_incident(
                con,
                trigger_environment=trigger_environment,
                trigger_emotion=trigger_emotion,
                application=application,
                duration_minutes=duration_minutes,
                note=note,
                day=day,
                slot_index=slot_index,
            )

    def complete_recovery(self, incident_id: int, recovery_action: str, next_step: str = "") -> dict[str, Any]:
        action_text = recovery_action.strip() or "完成 90 秒恢复协议"
        with self.connect() as con:
            incident = con.execute("SELECT * FROM incident_reports WHERE id=?", (incident_id,)).fetchone()
            if incident is None:
                raise ValueError("敌情报告不存在")
            if incident["recovered_at"]:
                return {"already_completed": True}
            stopped = datetime.fromisoformat(incident["stopped_at"] or incident["created_at"])
            delay = max(0, round((datetime.now() - stopped).total_seconds() / 60))
            con.execute(
                """UPDATE incident_reports SET recovered_at=?, recovery_action=?, next_step=?,
                   recovery_delay_minutes=? WHERE id=?""",
                (NOW(), action_text[:300], next_step.strip()[:500], delay, incident_id),
            )
            action_id = self._create_action(
                con, title="失控后重新开始", role_name="Guardian", category="恢复",
                action_date=incident["incident_date"], status="completed", tier="recovery"
            )
            con.execute(
                """UPDATE real_actions SET completed_at=?, output_type='恢复记录', output_text=?,
                   next_step=?, updated_at=? WHERE id=?""",
                (NOW(), action_text[:1000], next_step.strip()[:500], NOW(), action_id),
            )
            reward_result = self._award_action(
                con, action_id=action_id, role_name="Guardian", title="失控后成功恢复",
                tier="recovery", output_text=action_text, recovery=True,
            )
            self._apply_boss_delta(con, -7, "recovery", action_id, action_text)
            self._add_event(
                con, "recovery_complete", "恢复成功", f"停止下滑，并重新开始。恢复耗时 {delay} 分钟。",
                {"incident_id": incident_id, "delay": delay},
            )
        self._evaluate_growth_day(date.fromisoformat(incident["incident_date"]))
        positive = self._process_positive_rewards(date.fromisoformat(incident["incident_date"]))
        achievements = self.refresh_achievements()
        return {
            "quest_title": "失控后成功恢复", "recovery": True,
            "recovery_delay": delay, "positive_rewards": positive,
            "unlocked_achievements": achievements, **reward_result,
        }

    def get_incidents(self, day: date | None = None, unresolved_only: bool = False) -> list[dict[str, Any]]:
        day = day or date.today()
        sql = "SELECT * FROM incident_reports WHERE incident_date=?"
        params: list[Any] = [day.isoformat()]
        if unresolved_only:
            sql += " AND recovered_at IS NULL"
        sql += " ORDER BY id DESC"
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, params).fetchall()]

    def upsert_half_hour_record(
        self,
        slot_index: int,
        category: str,
        ownership_type: str = "planned_done",
        note: str = "",
        day: date | None = None,
        real_action_id: int | None = None,
        planned_category: str = "",
    ) -> dict[str, Any]:
        day = day or date.today()
        key = day.isoformat()
        slot = int(slot_index)
        if slot < 0 or slot > 47:
            raise ValueError("半小时槽位必须在 0 到 47 之间")
        clean = category.strip()[:60]
        if ownership_type == "owned":
            time_status = "planned_done"
        elif ownership_type == "unowned":
            time_status = "unowned"
        else:
            time_status = ownership_type
        if time_status not in TIME_STATUS_NAMES:
            raise ValueError("无效的时间状态")
        if not clean or time_status == "unrecorded":
            self.clear_half_hour_record(slot, day)
            return {"cleared": True, "slot_index": slot, "positive_rewards": []}
        # v2.2 only tracks the waking window 08:00–24:00. Historical records
        # outside this range may remain in the database, but cannot generate
        # actions, EXP, incidents or statistics.
        if not (TRACKING_START_SLOT <= slot < TRACKING_END_SLOT):
            with self.connect() as con:
                existing = con.execute(
                    "SELECT id FROM half_hour_records WHERE record_date=? AND slot_index=?", (key, slot)
                ).fetchone()
                now = NOW()
                if existing:
                    con.execute(
                        """UPDATE half_hour_records SET category=?,ownership_type='owned',note=?,rewarded=0,
                           real_action_id=NULL,planned_category=?,time_status='unrecorded',incident_id=NULL,
                           updated_at=? WHERE id=?""",
                        (clean, note.strip()[:500], planned_category.strip()[:60], now, existing["id"]),
                    )
                    record_id = int(existing["id"])
                else:
                    cur = con.execute(
                        """INSERT INTO half_hour_records(record_date,slot_index,category,ownership_type,note,
                           rewarded,created_at,updated_at,real_action_id,planned_category,time_status,incident_id)
                           VALUES(?,?,?,'owned',?,0,?,?,NULL,?,'unrecorded',NULL)""",
                        (key, slot, clean, note.strip()[:500], now, now, planned_category.strip()[:60]),
                    )
                    record_id = int(cur.lastrowid)
            return {"id": record_id, "slot_index": slot, "ignored_sleep_window": True,
                    "reward": 0, "exp": 0, "positive_rewards": []}
        derived_ownership = "unowned" if time_status == "unowned" else "owned"
        with self.connect() as con:
            existing = con.execute(
                "SELECT * FROM half_hour_records WHERE record_date=? AND slot_index=?", (key, slot)
            ).fetchone()
            incident_id = int(existing["incident_id"]) if existing and existing["incident_id"] else None
            reward_result: dict[str, Any] = {"reward": 0, "role_name": role_for_text(clean)}
            linked_action = int(existing["real_action_id"]) if existing and existing["real_action_id"] else real_action_id
            if time_status == "unowned":
                if incident_id is None:
                    incident_id = self._insert_incident(
                        con,
                        trigger_environment=planned_category or "时间轴记录",
                        trigger_emotion="",
                        application=clean,
                        duration_minutes=30,
                        note=note,
                        day=day,
                        slot_index=slot,
                    )
                linked_action = None
            else:
                linked_action, reward_result = self._find_or_create_slot_action(
                    con, key, slot, clean, note, linked_action
                )
            now = NOW()
            if existing:
                con.execute(
                    """UPDATE half_hour_records SET category=?,ownership_type=?,note=?,real_action_id=?,
                       planned_category=?,time_status=?,incident_id=?,updated_at=?,rewarded=1 WHERE id=?""",
                    (clean, derived_ownership, note.strip()[:500], linked_action, planned_category.strip()[:60],
                     time_status, incident_id, now, existing["id"]),
                )
                record_id = int(existing["id"])
            else:
                cur = con.execute(
                    """INSERT INTO half_hour_records(
                       record_date,slot_index,category,ownership_type,note,rewarded,created_at,updated_at,
                       real_action_id,planned_category,time_status,incident_id
                    ) VALUES(?,?,?,?,?,1,?,?,?,?,?,?)""",
                    (key, slot, clean, derived_ownership, note.strip()[:500], now, now,
                     linked_action, planned_category.strip()[:60], time_status, incident_id),
                )
                record_id = int(cur.lastrowid)
            self._add_event(
                con, "half_hour_log", "半小时已记录",
                f"{self.slot_label(slot)} · {clean} · {TIME_STATUS_NAMES[time_status]}",
                {"slot": slot, "time_status": time_status, "real_action_id": linked_action},
            )
        self._evaluate_growth_day(day)
        positive = self._process_positive_rewards(day)
        return {
            "id": record_id, "slot_index": slot, "real_action_id": linked_action,
            "incident_id": incident_id, "positive_rewards": positive,
            "exp": int(reward_result.get("reward", 0) or 0), **reward_result,
        }

    def add_time_entry(self, category: str, duration_minutes: int, ownership_type: str) -> dict[str, Any]:
        clean = category.strip()
        duration = int(duration_minutes)
        if not clean:
            raise ValueError("时间分类不能为空")
        if duration <= 0 or duration > 960:
            raise ValueError("时长必须在 1 到 960 分钟之间")
        status = "unowned" if ownership_type == "unowned" else "intentional_change"
        today = date.today().isoformat()
        with self.connect() as con:
            cur = con.execute(
                """INSERT INTO time_entries(category,duration_minutes,ownership_type,entry_date,created_at)
                   VALUES(?,?,?,?,?)""",
                (clean[:50], duration, "unowned" if status == "unowned" else "owned", today, NOW()),
            )
            entry_id = int(cur.lastrowid)
            if status == "unowned":
                incident_id = self._insert_incident(
                    con, application=clean, duration_minutes=duration, note="整段补录"
                )
                return {"id": entry_id, "exp": 0, "role_name": None, "incident_id": incident_id, "positive_rewards": []}
            role_name = role_for_text(clean) or "Mind"
            action_id = self._create_action(
                con, title=clean, role_name=role_name, category=clean,
                status="completed", tier="minimum"
            )
            con.execute(
                "UPDATE real_actions SET completed_at=?,output_type='整段时间记录',output_text=?,updated_at=? WHERE id=?",
                (NOW(), f"{duration} 分钟", NOW(), action_id),
            )
            con.execute("UPDATE time_entries SET real_action_id=? WHERE id=?", (action_id, entry_id))
            reward_result = self._award_action(
                con, action_id=action_id, role_name=role_name, title=clean, tier="minimum",
                output_text="", help_sought=False,
            )
        self._evaluate_growth_day(date.today())
        return {"id": entry_id, "real_action_id": action_id,
                "exp": int(reward_result.get("reward", 0) or 0),
                "positive_rewards": self._process_positive_rewards(date.today()), **reward_result}

    def get_half_hour_records(self, day: date | None = None) -> list[dict[str, Any]]:
        day = day or date.today()
        with self.connect() as con:
            rows = {
                int(r["slot_index"]): dict(r)
                for r in con.execute(
                    "SELECT * FROM half_hour_records WHERE record_date=? ORDER BY slot_index",
                    (day.isoformat(),),
                ).fetchall()
            }
        result: list[dict[str, Any]] = []
        for slot in range(TRACKING_START_SLOT, TRACKING_END_SLOT):
            row = rows.get(slot, {})
            status = row.get("time_status") or ("unowned" if row.get("ownership_type") == "unowned" else "planned_done")
            result.append({
                "id": row.get("id"), "record_date": day.isoformat(), "slot_index": slot,
                "start_time": self.slot_label(slot), "end_time": self.slot_label(slot + 1),
                "category": row.get("category", ""), "planned_category": row.get("planned_category", ""),
                "ownership_type": row.get("ownership_type", "owned"), "time_status": status,
                "note": row.get("note", ""), "rewarded": int(row.get("rewarded", 0) or 0),
                "real_action_id": row.get("real_action_id"), "incident_id": row.get("incident_id"),
            })
        return result

    def clear_half_hour_record(self, slot_index: int, day: date | None = None) -> None:
        day = day or date.today()
        with self.connect() as con:
            con.execute(
                """UPDATE half_hour_records SET category='',planned_category='',note='',ownership_type='owned',
                   time_status='unrecorded',real_action_id=NULL,incident_id=NULL,updated_at=?
                   WHERE record_date=? AND slot_index=?""",
                (NOW(), day.isoformat(), int(slot_index)),
            )

    def get_real_actions(self, day: date | None = None) -> list[dict[str, Any]]:
        day = day or date.today()
        with self.connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM real_actions WHERE action_date=? ORDER BY id", (day.isoformat(),)
            ).fetchall()]

    def get_active_actions(self, day: date | None = None) -> list[dict[str, Any]]:
        day = day or date.today()
        with self.connect() as con:
            return [dict(r) for r in con.execute(
                """SELECT * FROM real_actions WHERE action_date=? AND status IN ('started','completed')
                   ORDER BY status='started' DESC,id DESC""",
                (day.isoformat(),),
            ).fetchall()]

    def get_daily_checkin(self, day: date | None = None) -> dict[str, Any]:
        day = day or date.today()
        key = day.isoformat()
        with self.connect() as con:
            row = con.execute("SELECT * FROM daily_checkins WHERE checkin_date=?", (key,)).fetchone()
        if row:
            return dict(row)
        return {
            "checkin_date": key, "day_mode": "normal", "energy": 3, "mood": 3,
            "sleep_recovery": 3, "bedtime": "", "wake_time": "", "night_phone": 0,
            "daytime_sleepy": 0, "meals": 0, "protein": 0, "produce": 0, "water": 0,
            "evening_output": "", "evening_trigger": "", "next_physical_action": "",
        }

    def save_daily_checkin(self, day: date | None = None, **values: Any) -> dict[str, Any]:
        day = day or date.today()
        key = day.isoformat()
        current = self.get_daily_checkin(day)
        current.update(values)
        mode = current.get("day_mode", "normal")
        if mode not in DAY_MODE_NAMES:
            mode = "normal"
        with self.connect() as con:
            con.execute(
                """INSERT INTO daily_checkins(
                   checkin_date,day_mode,energy,mood,sleep_recovery,bedtime,wake_time,night_phone,
                   daytime_sleepy,meals,protein,produce,water,evening_output,evening_trigger,
                   next_physical_action,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(checkin_date) DO UPDATE SET
                   day_mode=excluded.day_mode,energy=excluded.energy,mood=excluded.mood,
                   sleep_recovery=excluded.sleep_recovery,bedtime=excluded.bedtime,wake_time=excluded.wake_time,
                   night_phone=excluded.night_phone,daytime_sleepy=excluded.daytime_sleepy,
                   meals=excluded.meals,protein=excluded.protein,produce=excluded.produce,water=excluded.water,
                   evening_output=excluded.evening_output,evening_trigger=excluded.evening_trigger,
                   next_physical_action=excluded.next_physical_action,updated_at=excluded.updated_at""",
                (
                    key, mode, max(1,min(5,_safe_int(current.get("energy"),3))),
                    max(1,min(5,_safe_int(current.get("mood"),3))),
                    max(1,min(5,_safe_int(current.get("sleep_recovery"),3))),
                    str(current.get("bedtime") or "")[:10], str(current.get("wake_time") or "")[:10],
                    int(bool(current.get("night_phone"))), int(bool(current.get("daytime_sleepy"))),
                    int(bool(current.get("meals"))), int(bool(current.get("protein"))),
                    int(bool(current.get("produce"))), int(bool(current.get("water"))),
                    str(current.get("evening_output") or "")[:1000],
                    str(current.get("evening_trigger") or "")[:1000],
                    str(current.get("next_physical_action") or "")[:500], NOW(),
                ),
            )
        self._evaluate_growth_day(day)
        return self.get_daily_status(day)

    def _day_criteria(self, con, day: date) -> dict[str, Any]:
        key = day.isoformat()
        checkin = con.execute("SELECT * FROM daily_checkins WHERE checkin_date=?", (key,)).fetchone()
        check = dict(checkin) if checkin else self.get_daily_checkin(day)
        actions = con.execute(
            "SELECT * FROM real_actions WHERE action_date=? AND status IN ('started','completed')",
            (key,),
        ).fetchall()
        incidents = con.execute(
            "SELECT * FROM incident_reports WHERE incident_date=?", (key,)
        ).fetchall()
        health_count = sum(int(check.get(k, 0) or 0) for k in ("meals", "protein", "produce", "water"))
        minimum_or_recovery = sum(1 for a in actions if a["tier"] in {"minimum", "recovery", "environment"})
        scholar_output = any(a["role_name"] == "Scholar" and str(a["output_text"] or "").strip() for a in actions)
        athlete = any(a["role_name"] == "Athlete" for a in actions)
        guardian = any(a["role_name"] == "Guardian" or a["tier"] in {"recovery", "environment"} for a in actions)
        review = bool(str(check.get("evening_output") or "").strip() and str(check.get("next_physical_action") or "").strip())
        quality = sum(int(a["quality_cycle"] or 0) for a in actions)
        challenge = sum(1 for a in actions if a["tier"] == "challenge")
        recovered = sum(1 for row in incidents if row["recovered_at"])
        survival_score = health_count + minimum_or_recovery + recovered
        normal_items = {
            "科研产物": scholar_output,
            "身体行动": athlete,
            "环境或恢复行动": guardian,
            "晚间收尾": review,
        }
        adventure_items = {**normal_items, "高质量工作循环": quality >= 1, "挑战版行动": challenge >= 1}
        return {
            "checkin": check,
            "actions": len(actions),
            "survival_score": survival_score,
            "survival_met": survival_score >= 2,
            "normal_items": normal_items,
            "normal_met": all(normal_items.values()),
            "adventure_items": adventure_items,
            "adventure_met": all(adventure_items.values()),
            "recovered": recovered,
            "quality_cycles": quality,
            "challenge_actions": challenge,
            "artifact_count": sum(1 for a in actions if a["tier"] not in {"recovery", "environment"} and str(a["output_text"] or "").strip()),
        }

    def _evaluate_growth_day(self, day: date) -> None:
        with self.connect() as con:
            criteria = self._day_criteria(con, day)
            mode = criteria["checkin"].get("day_mode", "normal")
            met = {
                "survival": criteria["survival_met"],
                "normal": criteria["normal_met"],
                "adventure": criteria["adventure_met"],
            }.get(mode, criteria["normal_met"])
            day_class = None
            source = ""
            if met:
                day_class = "maintenance" if mode == "survival" else "full"
                source = DAY_MODE_NAMES.get(mode, mode)
            elif criteria["recovered"] > 0:
                day_class = "recovery"
                source = "失控后恢复"
            if day_class:
                con.execute(
                    """INSERT INTO growth_days(growth_date,day_class,source,protected,created_at)
                       VALUES(?,?,?,?,?) ON CONFLICT(growth_date) DO UPDATE SET
                       day_class=excluded.day_class,source=excluded.source""",
                    (day.isoformat(), day_class, source, 0, NOW()),
                )

    def _protect_previous_day(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        with self.connect() as con:
            exists = con.execute("SELECT 1 FROM growth_days WHERE growth_date=?", (yesterday.isoformat(),)).fetchone()
            if exists:
                return
            player = con.execute("SELECT streak_shields FROM player WHERE id=1").fetchone()
            if not player or int(player["streak_shields"] or 0) <= 0:
                return
            # Only protect a day that truly had no completed action; never overwrite evidence.
            action_count = int(con.execute(
                "SELECT COUNT(*) c FROM real_actions WHERE action_date=?", (yesterday.isoformat(),)
            ).fetchone()["c"] or 0)
            if action_count:
                return
            con.execute("UPDATE player SET streak_shields=streak_shields-1 WHERE id=1")
            con.execute(
                "INSERT INTO growth_days(growth_date,day_class,source,protected,created_at) VALUES(?,?,?,?,?)",
                (yesterday.isoformat(), "recovery", "火种徽记保护", 1, NOW()),
            )
            self._add_event(con, "streak_protected", "火种已守住", "一次低谷没有抹去长期成长。", {})

    def get_growth_streak_breakdown(self) -> dict[str, int]:
        try:
            with self.connect() as con:
                rows = [dict(r) for r in con.execute(
                    "SELECT * FROM growth_days ORDER BY growth_date DESC"
                ).fetchall()]
        except sqlite3.OperationalError:
            legacy = original_get_streak(self)
            return {"total": legacy, "full": legacy, "maintenance": 0, "recovery": 0, "protected": 0}
        by_date = {date.fromisoformat(r["growth_date"]): r for r in rows}
        # Read legacy completed quest history too, including records imported
        # after the migration step. This keeps hidden streak quests truthful.
        try:
            with self.connect() as con:
                legacy_days = con.execute(
                    """SELECT DISTINCT quest_date FROM quests
                       WHERE status='completed' AND quest_date IS NOT NULL AND quest_date<>''"""
                ).fetchall()
            for item in legacy_days:
                legacy_day = date.fromisoformat(item["quest_date"])
                by_date.setdefault(legacy_day, {
                    "growth_date": legacy_day.isoformat(), "day_class": "full",
                    "protected": 0, "source": "旧版任务历史",
                })
        except (sqlite3.OperationalError, ValueError):
            pass
        cursor = date.today()
        if cursor not in by_date:
            cursor -= timedelta(days=1)
        result = {"total": 0, "full": 0, "maintenance": 0, "recovery": 0, "protected": 0}
        while cursor in by_date:
            row = by_date[cursor]
            result["total"] += 1
            result[row["day_class"]] = result.get(row["day_class"], 0) + 1
            result["protected"] += int(row["protected"] or 0)
            cursor -= timedelta(days=1)
        return result

    def get_streak(self) -> int:
        return self.get_growth_streak_breakdown()["total"]

    def get_daily_status(self, day: date | None = None) -> dict[str, Any]:
        day = day or date.today()
        with self.connect() as con:
            criteria = self._day_criteria(con, day)
            growth = con.execute("SELECT * FROM growth_days WHERE growth_date=?", (day.isoformat(),)).fetchone()
        mode = criteria["checkin"].get("day_mode", "normal")
        if mode == "survival":
            checklist = {
                "守住两项生命系统": criteria["survival_met"],
                f"当前维持分 {criteria['survival_score']} / 2": criteria["survival_met"],
            }
            progress = min(100, round(criteria["survival_score"] / 2 * 100))
            met = criteria["survival_met"]
        elif mode == "adventure":
            checklist = criteria["adventure_items"]
            progress = round(sum(checklist.values()) / len(checklist) * 100)
            met = criteria["adventure_met"]
        else:
            checklist = criteria["normal_items"]
            progress = round(sum(checklist.values()) / len(checklist) * 100)
            met = criteria["normal_met"]
        return {
            "date": day.isoformat(), "mode": mode, "mode_name": DAY_MODE_NAMES.get(mode, mode),
            "met": met, "progress": progress, "checklist": checklist,
            "day_class": growth["day_class"] if growth else "",
            "actions": criteria["actions"], "artifacts": criteria["artifact_count"],
            "quality_cycles": criteria["quality_cycles"], "recovered": criteria["recovered"],
            "checkin": criteria["checkin"],
        }

    def _process_positive_rewards(self, day: date | None = None) -> list[dict[str, Any]]:
        day = day or date.today()
        key = day.isoformat()
        rewards: list[dict[str, Any]] = []
        status = self.get_daily_status(day)
        with self.connect() as con:
            if status["met"]:
                claimed = self._claim_daily_reward(
                    con, key, f"DAY_VICTORY_{status['mode'].upper()}",
                    f"{status['mode_name']}胜利", "这一日按当前状态被完整接住。", 20, 20, 0,
                )
                if claimed:
                    rewards.append(claimed)
            if status["quality_cycles"]:
                claimed = self._claim_daily_reward(
                    con, key, "QUALITY_CYCLE", "高质量工作循环",
                    "完成工作、主动休息，并回到同一主线。", 15, 15, 0,
                )
                if claimed:
                    rewards.append(claimed)
            start = day - timedelta(days=day.weekday())
            growth_count = int(con.execute(
                "SELECT COUNT(*) c FROM growth_days WHERE growth_date BETWEEN ? AND ?",
                (start.isoformat(), day.isoformat()),
            ).fetchone()["c"] or 0)
            for threshold, exp, gold, shield in ((3, 20, 20, 0), (5, 35, 35, 1), (7, 50, 50, 0)):
                if growth_count >= threshold:
                    claimed = self._claim_daily_reward(
                        con, key, f"WEEK_STABILITY_{start.isoformat()}_{threshold}",
                        f"本周稳定性 {threshold} 天", "奖励长期稳定，而不是单日爆发。",
                        exp, gold, shield,
                    )
                    if claimed:
                        rewards.append(claimed)
        return rewards

    def get_daily_reward_state(self, day: date | None = None) -> dict[str, Any]:
        day = day or date.today()
        status = self.get_daily_status(day)
        with self.connect() as con:
            claimed = [dict(r) for r in con.execute(
                "SELECT * FROM daily_reward_claims WHERE reward_date=? ORDER BY id", (day.isoformat(),)
            ).fetchall()]
            shields = int(con.execute("SELECT streak_shields FROM player WHERE id=1").fetchone()[0] or 0)
        target = {"survival": 2, "normal": 4, "adventure": 6}.get(status["mode"], 4)
        return {
            "actions": status["actions"], "focus_chain": status["quality_cycles"],
            "quality_cycles": status["quality_cycles"], "claimed": claimed,
            "next_threshold": target, "momentum": status["progress"],
            "label": f"{status['mode_name']} · {'已胜利' if status['met'] else '进行中'}",
            "streak_shields": shields, "day_status": status,
        }

    def get_today_summary(self) -> dict[str, int]:
        today = date.today().isoformat()
        with self.connect() as con:
            q = con.execute(
                """SELECT COUNT(*) total,SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed
                   FROM quests WHERE quest_date=? AND quest_type='daily' AND status!='deleted'""",
                (today,),
            ).fetchone()
            slots = con.execute(
                """SELECT COUNT(*) recorded,
                   SUM(CASE WHEN time_status IN ('planned_done','intentional_change') THEN 1 ELSE 0 END) owned,
                   SUM(CASE WHEN time_status='unowned' THEN 1 ELSE 0 END) lost
                   FROM half_hour_records WHERE record_date=? AND category<>''
                   AND slot_index>=? AND slot_index<?""",
                (today, TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchone()
            ledger = con.execute(
                "SELECT COALESCE(SUM(exp),0) exp,COALESCE(SUM(gold),0) gold FROM reward_ledger WHERE reward_date=?",
                (today,),
            ).fetchone()
        recorded = int(slots["recorded"] or 0)
        owned_slots = int(slots["owned"] or 0)
        denominator = TRACKING_SLOT_COUNT
        state = self.get_daily_reward_state()
        streak = self.get_growth_streak_breakdown()
        return {
            "quest_total": int(q["total"] or 0), "quest_completed": int(q["completed"] or 0),
            "today_exp": int(ledger["exp"] or 0), "today_gold": int(ledger["gold"] or 0),
            "time_total": recorded * 30, "time_owned": owned_slots * 30,
            "ownership": round(owned_slots / denominator * 100),
            "coverage": round(recorded / denominator * 100),
            "streak": streak["total"], "actions": state["actions"],
            "momentum": state["momentum"], "focus_chain": state["quality_cycles"],
            "streak_shields": state["streak_shields"], "lost_slots": int(slots["lost"] or 0),
        }

    def get_weekly_stats(self, days: int = 7, end_day: date | None = None) -> dict[str, Any]:
        end = end_day or date.today()
        start = end - timedelta(days=days - 1)
        with self.connect() as con:
            categories = [dict(r) for r in con.execute(
                """SELECT category,COUNT(*)*30 minutes FROM half_hour_records
                   WHERE record_date BETWEEN ? AND ? AND category<>''
                   AND slot_index>=? AND slot_index<? GROUP BY category ORDER BY minutes DESC""",
                (start.isoformat(), end.isoformat(), TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchall()]
            quest_rows = {r["quest_date"]: dict(r) for r in con.execute(
                """SELECT quest_date,SUM(status='completed') completed,COUNT(*) total FROM quests
                   WHERE quest_type='daily' AND status!='deleted' AND quest_date BETWEEN ? AND ?
                   GROUP BY quest_date""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()}
            time_rows = {r["record_date"]: dict(r) for r in con.execute(
                """SELECT record_date,COUNT(*) recorded,
                   SUM(time_status IN ('planned_done','intentional_change')) owned,
                   SUM(time_status='unowned') lost FROM half_hour_records
                   WHERE record_date BETWEEN ? AND ? AND category<>''
                   AND slot_index>=? AND slot_index<? GROUP BY record_date""",
                (start.isoformat(), end.isoformat(), TRACKING_START_SLOT, TRACKING_END_SLOT),
            ).fetchall()}
            role_exp = [dict(r) for r in con.execute(
                """SELECT r.name,COALESCE(SUM(l.exp),0) exp FROM roles r LEFT JOIN reward_ledger l
                   ON l.role_name=r.name AND l.reward_date BETWEEN ? AND ? GROUP BY r.id ORDER BY r.id""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()]
            ledger = con.execute(
                "SELECT COALESCE(SUM(exp),0) exp,COALESCE(SUM(gold),0) gold FROM reward_ledger WHERE reward_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            marks = con.execute(
                "SELECT COALESCE(SUM(shield_reward),0) value FROM daily_reward_claims WHERE reward_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            triggers = [dict(r) for r in con.execute(
                """SELECT CASE WHEN trigger_environment<>'' THEN trigger_environment
                                WHEN trigger_emotion<>'' THEN trigger_emotion ELSE application END trigger,
                          COUNT(*) count FROM incident_reports WHERE incident_date BETWEEN ? AND ?
                   GROUP BY trigger ORDER BY count DESC LIMIT 3""",
                (start.isoformat(), end.isoformat()),
            ).fetchall()]
            extras = con.execute(
                """SELECT COALESCE(AVG(NULLIF(launch_delay_minutes,0)),0) avg_delay,
                   SUM(CASE WHEN output_text<>'' AND tier NOT IN ('recovery','environment') THEN 1 ELSE 0 END) artifacts,
                   SUM(CASE WHEN quality_cycle=1 THEN 1 ELSE 0 END) cycles
                   FROM real_actions WHERE action_date BETWEEN ? AND ?""",
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            growth = [dict(r) for r in con.execute(
                "SELECT * FROM growth_days WHERE growth_date BETWEEN ? AND ? ORDER BY growth_date",
                (start.isoformat(), end.isoformat()),
            ).fetchall()]
        daily: list[dict[str, Any]] = []
        cursor = start
        total_recorded = total_owned = 0
        while cursor <= end:
            key = cursor.isoformat()
            q = quest_rows.get(key, {})
            t = time_rows.get(key, {})
            recorded = int(t.get("recorded", 0) or 0)
            owned = int(t.get("owned", 0) or 0)
            total_recorded += recorded
            total_owned += owned
            daily.append({
                "quest_date": key, "completed": int(q.get("completed", 0) or 0),
                "total": int(q.get("total", 0) or 0), "minutes": recorded * 30,
                "owned_minutes": owned * 30, "coverage": round(recorded / TRACKING_SLOT_COUNT * 100),
                "ownership": round(owned / TRACKING_SLOT_COUNT * 100),
            })
            cursor += timedelta(days=1)
        classes = {"full": 0, "maintenance": 0, "recovery": 0}
        for row in growth:
            classes[row["day_class"]] = classes.get(row["day_class"], 0) + 1
        return {
            "start": start, "end": end, "categories": categories, "daily": daily,
            "role_exp": role_exp,
            "ownership": round(total_owned / (TRACKING_SLOT_COUNT * days) * 100),
            "coverage": round(total_recorded / (TRACKING_SLOT_COUNT * days) * 100),
            "total_minutes": total_recorded * 30, "total_exp": int(ledger["exp"] or 0),
            "total_gold": int(ledger["gold"] or 0), "total_marks": int(marks["value"] or 0),
            "top_triggers": triggers, "avg_launch_delay": round(float(extras["avg_delay"] or 0), 1),
            "artifact_count": int(extras["artifacts"] or 0), "quality_cycles": int(extras["cycles"] or 0),
            "growth_classes": classes,
        }

    def save_phone_environment(self, parking_location: str, bedtime_charge_location: str, focus_rule: str) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO phone_environment(id,parking_location,bedtime_charge_location,focus_rule,updated_at)
                   VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                   parking_location=excluded.parking_location,
                   bedtime_charge_location=excluded.bedtime_charge_location,
                   focus_rule=excluded.focus_rule,updated_at=excluded.updated_at""",
                (parking_location[:200], bedtime_charge_location[:200], focus_rule[:500], NOW()),
            )

    def get_phone_environment(self) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT * FROM phone_environment WHERE id=1").fetchone()
            return dict(row) if row else {}

    def record_environment_action(self, title: str, detail: str = "") -> dict[str, Any]:
        with self.connect() as con:
            action_id = self._create_action(
                con, title=title, role_name="Guardian", category="环境工程",
                status="completed", tier="environment"
            )
            con.execute(
                "UPDATE real_actions SET completed_at=?,output_type='环境调整',output_text=?,updated_at=? WHERE id=?",
                (NOW(), detail[:1000], NOW(), action_id),
            )
            result = self._award_action(
                con, action_id=action_id, role_name="Guardian", title=title,
                tier="environment", output_text=detail,
            )
        self._evaluate_growth_day(date.today())
        return {"quest_title": title, "environment": True, "positive_rewards": self._process_positive_rewards(date.today()), **result}

    def save_weekly_review(self, week_end: date, helped: str, repeated_failure: str, next_experiment: str) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO weekly_reviews(week_end,helped,repeated_failure,next_experiment,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(week_end) DO UPDATE SET
                   helped=excluded.helped,repeated_failure=excluded.repeated_failure,
                   next_experiment=excluded.next_experiment,updated_at=excluded.updated_at""",
                (week_end.isoformat(), helped[:2000], repeated_failure[:2000], next_experiment[:2000], NOW()),
            )

    def get_weekly_review(self, week_end: date | None = None) -> dict[str, Any]:
        week_end = week_end or date.today()
        with self.connect() as con:
            row = con.execute("SELECT * FROM weekly_reviews WHERE week_end=?", (week_end.isoformat(),)).fetchone()
        return dict(row) if row else {"week_end": week_end.isoformat(), "helped": "", "repeated_failure": "", "next_experiment": ""}

    def get_active_season(self) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT * FROM seasons WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else {}

    def save_active_season(self, title: str, start: date, end: date, primary: str, maintenance: str) -> None:
        if end < start:
            raise ValueError("赛季结束日期不能早于开始日期")
        with self.connect() as con:
            current = con.execute("SELECT id FROM seasons WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            if current:
                con.execute(
                    """UPDATE seasons SET title=?,start_date=?,end_date=?,primary_goals=?,maintenance_goals=? WHERE id=?""",
                    (title[:120], start.isoformat(), end.isoformat(), primary[:2000], maintenance[:2000], current["id"]),
                )
            else:
                con.execute(
                    """INSERT INTO seasons(title,start_date,end_date,primary_goals,maintenance_goals,status,created_at)
                       VALUES(?,?,?,?,?,'active',?)""",
                    (title[:120], start.isoformat(), end.isoformat(), primary[:2000], maintenance[:2000], NOW()),
                )

    def get_athlete_profile(self) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT * FROM athlete_profile WHERE id=1").fetchone()
            return dict(row) if row else {}

    def save_athlete_profile(self, **values: Any) -> dict[str, Any]:
        numeric = (
            "height_cm", "weight_kg", "standing_reach_cm", "standing_jump_cm", "approach_jump_cm",
            "time_30m", "time_100m", "time_200m", "time_300m", "time_400m",
        )
        with self.connect() as con:
            sets = [f"{name}=?" for name in numeric]
            params = [values.get(name) if values.get(name) not in {"", None} else None for name in numeric]
            sets += ["strength_baseline=?", "pain_location=?", "pain_score=?", "fatigue=?", "recovery=?", "updated_at=?"]
            params += [
                str(values.get("strength_baseline") or "")[:1000],
                str(values.get("pain_location") or "")[:300],
                max(0,min(10,_safe_int(values.get("pain_score"),0))),
                max(1,min(5,_safe_int(values.get("fatigue"),3))),
                max(1,min(5,_safe_int(values.get("recovery"),3))), NOW(), 1,
            ]
            con.execute(f"UPDATE athlete_profile SET {','.join(sets)} WHERE id=?", params)
        state = self.get_athlete_risk_state()
        minimum, standard, challenge = _default_tiers("今日身体行动", "Athlete")
        with self.connect() as con:
            if state["risk"]:
                con.execute(
                    """UPDATE quests SET title='今日身体恢复行动',
                       minimum_text='做 5 分钟关节活动、散步或轻柔恢复',
                       standard_text='完成低负荷恢复、技术或康复训练',
                       challenge_text='完成恢复训练并记录疼痛、疲劳与下一步'
                       WHERE quest_date=? AND quest_type='daily' AND status='pending'
                       AND title IN ('今日身体行动','今日身体恢复行动')""",
                    (date.today().isoformat(),),
                )
            else:
                con.execute(
                    """UPDATE quests SET title='今日身体行动',minimum_text=?,standard_text=?,challenge_text=?
                       WHERE quest_date=? AND quest_type='daily' AND status='pending'
                       AND title='今日身体恢复行动'""",
                    (minimum, standard, challenge, date.today().isoformat()),
                )
        state["task_adjusted"] = bool(state["risk"])
        return state

    def get_athlete_risk_state(self) -> dict[str, Any]:
        profile = self.get_athlete_profile()
        pain = _safe_int(profile.get("pain_score"), 0)
        fatigue = _safe_int(profile.get("fatigue"), 3)
        recovery = _safe_int(profile.get("recovery"), 3)
        risk = pain >= 4 or fatigue >= 5 or recovery <= 1
        reasons = []
        if pain >= 4:
            reasons.append("疼痛达到 4/10 或以上")
        if fatigue >= 5:
            reasons.append("主观疲劳很高")
        if recovery <= 1:
            reasons.append("恢复感很差")
        return {"risk": risk, "reasons": reasons, "profile": profile}

    def add_guitar_session(self, **values: Any) -> int:
        with self.connect() as con:
            cur = con.execute(
                """INSERT INTO guitar_sessions(session_date,technique,repertoire,ear_theory,expression,
                   recording_path,note,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    str(values.get("session_date") or date.today().isoformat()),
                    str(values.get("technique") or "")[:500], str(values.get("repertoire") or "")[:500],
                    str(values.get("ear_theory") or "")[:500], str(values.get("expression") or "")[:500],
                    str(values.get("recording_path") or "")[:1000], str(values.get("note") or "")[:1000], NOW(),
                ),
            )
            session_id = int(cur.lastrowid)
            action_id = self._create_action(
                con, title="吉他结构化练习", role_name="Bard", category="吉他",
                status="completed", tier="standard"
            )
            output = str(values.get("recording_path") or values.get("expression") or values.get("repertoire") or "")
            con.execute(
                "UPDATE real_actions SET completed_at=?,output_type='练习记录',output_text=?,updated_at=? WHERE id=?",
                (NOW(), output[:1000], NOW(), action_id),
            )
            self._award_action(
                con, action_id=action_id, role_name="Bard", title="吉他结构化练习",
                tier="standard", output_text=output,
            )
        self._evaluate_growth_day(date.today())
        return session_id

    def get_guitar_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM guitar_sessions ORDER BY session_date DESC,id DESC LIMIT ?", (limit,)
            ).fetchall()]

    def refresh_achievements(self) -> list[str]:
        unlocked = original_refresh_achievements(self)
        try:
            with self.connect() as probe:
                probe.execute("SELECT 1 FROM real_actions LIMIT 1")
                probe.execute("SELECT 1 FROM incident_reports LIMIT 1")
        except sqlite3.OperationalError:
            return unlocked
        with self.connect() as con:
            values = {
                "RECOVERY_10": int(con.execute("SELECT COUNT(*) c FROM incident_reports WHERE recovered_at IS NOT NULL").fetchone()["c"] or 0),
                "OUTPUT_10": int(con.execute("SELECT COUNT(*) c FROM real_actions WHERE output_text<>''").fetchone()["c"] or 0),
                "START_DELAY_5": int(con.execute("SELECT COUNT(*) c FROM real_actions WHERE launch_delay_minutes BETWEEN 1 AND 5").fetchone()["c"] or 0),
                "QUALITY_CYCLE_5": int(con.execute("SELECT COUNT(*) c FROM real_actions WHERE quality_cycle=1").fetchone()["c"] or 0),
            }
            for code, value in values.items():
                row = con.execute("SELECT * FROM achievements WHERE code=?", (code,)).fetchone()
                if row is None:
                    continue
                completed_at = row["completed_at"]
                if not completed_at and value >= int(row["target_value"]):
                    completed_at = NOW()
                    title = row["title"]
                    self._add_event(con, "achievement_unlock", "成就解锁", title, {"code": code})
                    unlocked.append(title)
                con.execute(
                    "UPDATE achievements SET current_value=?,completed_at=? WHERE code=?",
                    (min(value, int(row["target_value"])), completed_at, code),
                )
        return unlocked

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        quests = [dict(q) for q in self.get_today_quests()]
        pending = [q for q in quests if q["status"] == "pending"]
        return {
            "player": dict(self.get_player()), "roles": [dict(r) for r in self.get_roles()],
            "quests": quests, "next_quest": pending[0] if pending else None,
            "summary": self.get_today_summary(), "day_status": self.get_daily_status(),
            "growth": self.get_growth_streak_breakdown(),
            "boss": dict(self.get_active_boss()) if self.get_active_boss() else None,
            "main_quest": dict(self.get_main_quest()) if self.get_main_quest() else None,
            "events": [dict(e) for e in self.get_recent_events(5)],
        }

    # Bind extension methods.
    Database.initialize = initialize
    Database.ensure_daily_quests = ensure_daily_quests
    Database.add_quest = add_quest
    Database.start_quest_action = start_quest_action
    Database.complete_quest = complete_quest
    Database.upsert_half_hour_record = upsert_half_hour_record
    Database.add_time_entry = add_time_entry
    Database.get_half_hour_records = get_half_hour_records
    Database.clear_half_hour_record = clear_half_hour_record
    Database.get_real_actions = get_real_actions
    Database.get_active_actions = get_active_actions
    Database.log_incident = log_incident
    Database.complete_recovery = complete_recovery
    Database.get_incidents = get_incidents
    Database.get_daily_checkin = get_daily_checkin
    Database.save_daily_checkin = save_daily_checkin
    Database.get_daily_status = get_daily_status
    Database.get_growth_streak_breakdown = get_growth_streak_breakdown
    Database.get_streak = get_streak
    Database.get_daily_reward_state = get_daily_reward_state
    Database.get_today_summary = get_today_summary
    Database.get_weekly_stats = get_weekly_stats
    Database.save_phone_environment = save_phone_environment
    Database.get_phone_environment = get_phone_environment
    Database.record_environment_action = record_environment_action
    Database.save_weekly_review = save_weekly_review
    Database.get_weekly_review = get_weekly_review
    Database.get_active_season = get_active_season
    Database.save_active_season = save_active_season
    Database.get_athlete_profile = get_athlete_profile
    Database.save_athlete_profile = save_athlete_profile
    Database.get_athlete_risk_state = get_athlete_risk_state
    Database.add_guitar_session = add_guitar_session
    Database.get_guitar_sessions = get_guitar_sessions
    Database.refresh_achievements = refresh_achievements
    Database.get_dashboard_snapshot = get_dashboard_snapshot
    Database._migrate_v22 = _migrate_v22
    Database._row_with_role = _row_with_role
    Database._role_exp_used = _role_exp_used
    Database._find_or_create_slot_action = _find_or_create_slot_action
    Database._insert_incident = _insert_incident
    Database._create_action = _create_action
    Database._calculate_action_exp = _calculate_action_exp
    Database._award_action = _award_action
    Database._process_positive_rewards = _process_positive_rewards
    Database._evaluate_growth_day = _evaluate_growth_day
    Database._protect_previous_day = _protect_previous_day
    Database._day_criteria = _day_criteria

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from database.connection import Database
from mobile_widgets import (
    CompletionDialog,
    IncidentDialog,
    MetricCard,
    ScrollPage,
    Section,
    SlotDialog,
)
from system.level import exp_needed
from system.localization import role_display
from system.time_window import TRACKING_END_SLOT, TRACKING_START_SLOT


def clear_layout(layout: QVBoxLayout | QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


class HomePage(ScrollPage):
    changed = Signal()
    open_tasks = Signal()
    open_timeline = Signal()

    def __init__(self, db: Database):
        super().__init__("EARTH ONLINE", "现实人生 RPG · 只奖励现实行动")
        self.db = db

        self.identity = QLabel()
        self.identity.setObjectName("mobileHero")
        self.identity.setWordWrap(True)
        self.layout.addWidget(self.identity)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(8)
        metric_grid.setVerticalSpacing(8)
        self.level = MetricCard("账号等级")
        self.exp = MetricCard("今日经验")
        self.ownership = MetricCard("时间所有权")
        self.streak = MetricCard("连续成长")
        for index, card in enumerate((self.level, self.exp, self.ownership, self.streak)):
            metric_grid.addWidget(card, index // 2, index % 2)
        self.layout.addLayout(metric_grid)

        day = Section("今日状态")
        self.day_label = QLabel()
        self.day_label.setObjectName("mobileStrong")
        self.day_progress = QProgressBar()
        self.day_progress.setRange(0, 100)
        self.day_detail = QLabel()
        self.day_detail.setObjectName("mobileMuted")
        self.day_detail.setWordWrap(True)
        day.layout.addWidget(self.day_label)
        day.layout.addWidget(self.day_progress)
        day.layout.addWidget(self.day_detail)
        self.layout.addWidget(day)

        next_section = Section("下一步行动")
        self.next_title = QLabel()
        self.next_title.setObjectName("mobileActionTitle")
        self.next_title.setWordWrap(True)
        self.next_tiers = QLabel()
        self.next_tiers.setObjectName("mobileMuted")
        self.next_tiers.setWordWrap(True)
        button_row = QHBoxLayout()
        self.start_button = QPushButton("开始下一步")
        self.start_button.setObjectName("mobilePrimary")
        self.start_button.clicked.connect(self._start_next)
        self.complete_button = QPushButton("完成并结算")
        self.complete_button.clicked.connect(self._complete_next)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.complete_button)
        next_section.layout.addWidget(self.next_title)
        next_section.layout.addWidget(self.next_tiers)
        next_section.layout.addLayout(button_row)
        self.layout.addWidget(next_section)

        quick = Section("快速入口")
        task_btn = QPushButton("查看全部今日任务")
        task_btn.clicked.connect(self.open_tasks.emit)
        time_btn = QPushButton("记录当前半小时")
        time_btn.clicked.connect(self.open_timeline.emit)
        quick.layout.addWidget(task_btn)
        quick.layout.addWidget(time_btn)
        self.layout.addWidget(quick)

        roles = Section("职业成长")
        self.roles_layout = QVBoxLayout()
        roles.layout.addLayout(self.roles_layout)
        self.layout.addWidget(roles)

        boss = Section("当前首领")
        self.boss_label = QLabel()
        self.boss_label.setWordWrap(True)
        self.boss_bar = QProgressBar()
        self.boss_bar.setTextVisible(True)
        boss.layout.addWidget(self.boss_label)
        boss.layout.addWidget(self.boss_bar)
        self.layout.addWidget(boss)
        self.layout.addStretch()
        self.snapshot: dict = {}

    def refresh(self) -> None:
        self.snapshot = self.db.get_dashboard_snapshot()
        player = self.snapshot["player"]
        summary = self.snapshot["summary"]
        status = self.snapshot["day_status"]
        self.identity.setText(f"{player['name']}\n{player['title']} · {player['account_level']} 级")
        self.level.set_value(player["account_level"])
        self.exp.set_value(f"{summary['today_exp']} 经验")
        self.ownership.set_value(f"{summary['ownership']}%")
        self.streak.set_value(f"{summary['streak']} 天")
        self.day_label.setText(f"{status['mode_name']} · {'胜利' if status['met'] else '进行中'}")
        self.day_progress.setValue(int(status["progress"]))
        checklist = " · ".join(f"{'✓' if ok else '○'} {name}" for name, ok in status["checklist"].items())
        self.day_detail.setText(checklist)

        quest = self.snapshot.get("next_quest")
        if quest:
            self.next_title.setText(str(quest["title"]))
            self.next_tiers.setText(
                f"最低版：{quest.get('minimum_text','')}\n"
                f"标准版：{quest.get('standard_text','')}\n"
                f"挑战版：{quest.get('challenge_text','')}"
            )
            self.start_button.setEnabled(True)
            self.complete_button.setEnabled(True)
        else:
            self.next_title.setText("今日任务已经全部完成")
            self.next_tiers.setText("可以收尾、恢复，或者主动选择下一项现实行动。")
            self.start_button.setEnabled(False)
            self.complete_button.setEnabled(False)

        clear_layout(self.roles_layout)
        for role in self.snapshot["roles"]:
            row = QFrame()
            row.setObjectName("mobileSubCard")
            lay = QVBoxLayout(row)
            lay.setContentsMargins(10, 8, 10, 8)
            top = QLabel(f"{role_display(role['name'])} · {role['level']} 级")
            bar = QProgressBar()
            needed = exp_needed(int(role["level"]))
            bar.setRange(0, needed)
            bar.setValue(int(role["exp"]))
            bar.setFormat(f"{role['exp']} / {needed} 经验")
            lay.addWidget(top)
            lay.addWidget(bar)
            self.roles_layout.addWidget(row)

        boss = self.snapshot.get("boss")
        if boss:
            self.boss_label.setText(f"{boss['name']}\n弱点：{boss['weaknesses']}")
            self.boss_bar.setRange(0, int(boss["max_hp"]))
            self.boss_bar.setValue(int(boss["hp"]))
            self.boss_bar.setFormat(f"生命 {boss['hp']} / {boss['max_hp']}")
        else:
            self.boss_label.setText("当前没有活动首领")
            self.boss_bar.setRange(0, 1)
            self.boss_bar.setValue(0)

    def _next(self) -> dict | None:
        return self.snapshot.get("next_quest")

    def _start_next(self) -> None:
        quest = self._next()
        if not quest:
            return
        result = self.db.start_quest_action(int(quest["id"]))
        info(self, "已经开始", f"{quest['title']}\n启动奖励：+{result.get('reward', 0)} 经验\n现在离开游戏，去做现实行动。")
        self.changed.emit()

    def _complete_next(self) -> None:
        quest = self._next()
        if not quest:
            return
        dialog = CompletionDialog(str(quest["title"]), self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            result = self.db.complete_quest(int(quest["id"]), dialog.data())
        except ValueError as exc:
            QMessageBox.warning(self, "无法结算", str(exc))
            return
        info(self, "现实行动完成", f"{quest['title']}\n+{result.get('reward', 0)} 经验")
        self.changed.emit()


class TasksPage(ScrollPage):
    changed = Signal()

    def __init__(self, db: Database):
        super().__init__("任务日志", "最低版、标准版和挑战版都是有效的现实行动。")
        self.db = db
        add = QPushButton("＋ 新建今日任务")
        add.setObjectName("mobilePrimary")
        add.clicked.connect(self._add_task)
        self.layout.addWidget(add)
        self.tasks_layout = QVBoxLayout()
        self.tasks_layout.setSpacing(10)
        self.layout.addLayout(self.tasks_layout)
        self.layout.addStretch()

    def refresh(self) -> None:
        clear_layout(self.tasks_layout)
        quests = [dict(q) for q in self.db.get_today_quests()]
        if not quests:
            self.tasks_layout.addWidget(QLabel("今天还没有任务。"))
        for quest in quests:
            card = Section(str(quest["title"]))
            state = "已完成" if quest["status"] == "completed" else role_display(quest["role_name"])
            state_label = QLabel(f"{state} · 核心奖励只结算一次")
            state_label.setObjectName("mobileMuted")
            card.layout.addWidget(state_label)
            tiers = QLabel(
                f"最低：{quest.get('minimum_text','')}\n"
                f"标准：{quest.get('standard_text','')}\n"
                f"挑战：{quest.get('challenge_text','')}"
            )
            tiers.setWordWrap(True)
            tiers.setObjectName("mobileMuted")
            card.layout.addWidget(tiers)
            row = QHBoxLayout()
            start = QPushButton("开始")
            complete = QPushButton("完成")
            complete.setObjectName("mobilePrimary")
            start.setEnabled(quest["status"] == "pending")
            complete.setEnabled(quest["status"] == "pending")
            start.clicked.connect(lambda _=False, q=quest: self._start(q))
            complete.clicked.connect(lambda _=False, q=quest: self._complete(q))
            row.addWidget(start)
            row.addWidget(complete)
            card.layout.addLayout(row)
            self.tasks_layout.addWidget(card)

    def _start(self, quest: dict) -> None:
        result = self.db.start_quest_action(int(quest["id"]))
        info(self, "已经开始", f"{quest['title']}\n+{result.get('reward', 0)} 经验")
        self.changed.emit()

    def _complete(self, quest: dict) -> None:
        dialog = CompletionDialog(str(quest["title"]), self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            result = self.db.complete_quest(int(quest["id"]), dialog.data())
        except ValueError as exc:
            QMessageBox.warning(self, "无法结算", str(exc))
            return
        info(self, "完成", f"获得 {result.get('reward', 0)} 经验")
        self.changed.emit()

    def _add_task(self) -> None:
        title, ok = QInputDialog.getText(self, "新建今日任务", "任务名称：")
        if not ok or not title.strip():
            return
        roles = [dict(r) for r in self.db.get_roles()]
        names = [role_display(r["name"]) for r in roles]
        selected, ok = QInputDialog.getItem(self, "选择职业", "这项行动主要成长哪条道路？", names, 0, False)
        if not ok:
            return
        role = roles[names.index(selected)]
        self.db.add_quest(title.strip(), int(role["id"]), 10, "daily")
        self.changed.emit()


class TimelinePage(ScrollPage):
    changed = Signal()

    def __init__(self, db: Database):
        super().__init__("半小时记录", "只记录 08:00–24:00。睡眠不需要逐格填写。")
        self.db = db
        self.current_button = QPushButton("记录当前半小时")
        self.current_button.setObjectName("mobilePrimary")
        self.current_button.clicked.connect(self._edit_current)
        self.layout.addWidget(self.current_button)
        self.coverage = QLabel()
        self.coverage.setObjectName("mobileMuted")
        self.layout.addWidget(self.coverage)
        self.slots_layout = QVBoxLayout()
        self.slots_layout.setSpacing(6)
        self.layout.addLayout(self.slots_layout)
        self.layout.addStretch()
        self.records: dict[int, dict] = {}

    def refresh(self) -> None:
        rows = self.db.get_half_hour_records(date.today())
        self.records = {int(r["slot_index"]): dict(r) for r in rows}
        clear_layout(self.slots_layout)
        for slot in range(TRACKING_START_SLOT, TRACKING_END_SLOT):
            record = self.records.get(slot)
            label = self.db.slot_label(slot)
            text = label
            if record and record.get("category"):
                status_map = {
                    "planned_done": "完成",
                    "intentional_change": "主动调整",
                    "unowned": "失控",
                    "unrecorded": "未记录",
                }
                text += f"  ·  {record['category']}  ·  {status_map.get(record.get('time_status'), '')}"
            else:
                text += "  ·  未记录"
            button = QPushButton(text)
            button.setObjectName("mobileSlotLost" if record and record.get("time_status") == "unowned" else "mobileSlot")
            button.setProperty("slot_index", slot)
            button.clicked.connect(lambda _=False, s=slot: self._edit_slot(s))
            self.slots_layout.addWidget(button)
        summary = self.db.get_today_summary()
        self.coverage.setText(
            f"记录覆盖 {summary['coverage']}% · 时间所有权 {summary['ownership']}% · "
            "主动调整仍属于主动时间"
        )

    def _current_slot(self) -> int:
        now = datetime.now()
        slot = now.hour * 2 + (1 if now.minute >= 30 else 0)
        return max(TRACKING_START_SLOT, min(TRACKING_END_SLOT - 1, slot))

    def _edit_current(self) -> None:
        self._edit_slot(self._current_slot())

    def _edit_slot(self, slot: int) -> None:
        dialog = SlotDialog(self.db.slot_label(slot), self.records.get(slot), self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.data()
        if data["time_status"] == "unrecorded" or not data["category"]:
            self.db.clear_half_hour_record(slot, date.today())
        else:
            self.db.upsert_half_hour_record(
                slot,
                data["category"],
                data["time_status"],
                data["note"],
                date.today(),
            )
        self.changed.emit()


class RecoveryPage(ScrollPage):
    changed = Signal()

    def __init__(self, db: Database):
        super().__init__("恢复营地", "状态差时降低目标；失控后奖励重新开始。")
        self.db = db

        checkin = Section("晨间状态")
        self.mode = QComboBox()
        self.mode.addItem("生存日", "survival")
        self.mode.addItem("正常日", "normal")
        self.mode.addItem("冒险日", "adventure")
        self.energy = QSlider(Qt.Orientation.Horizontal)
        self.energy.setRange(1, 5)
        self.mood = QSlider(Qt.Orientation.Horizontal)
        self.mood.setRange(1, 5)
        self.sleep = QSlider(Qt.Orientation.Horizontal)
        self.sleep.setRange(1, 5)
        self.energy_label = QLabel()
        self.mood_label = QLabel()
        self.sleep_label = QLabel()
        for slider, label, prefix in (
            (self.energy, self.energy_label, "能量"),
            (self.mood, self.mood_label, "情绪"),
            (self.sleep, self.sleep_label, "睡眠恢复"),
        ):
            slider.valueChanged.connect(lambda value, lab=label, pre=prefix: lab.setText(f"{pre}：{value} / 5"))
            checkin.layout.addWidget(label)
            checkin.layout.addWidget(slider)
        checkin.layout.insertWidget(1, self.mode)
        self.meals = QCheckBox("规律吃了主要餐食")
        self.protein = QCheckBox("摄入蛋白质来源")
        self.produce = QCheckBox("吃了蔬菜或水果")
        self.water = QCheckBox("喝了足够的水")
        for box in (self.meals, self.protein, self.produce, self.water):
            checkin.layout.addWidget(box)
        self.next_action = QLineEdit()
        self.next_action.setPlaceholderText("明天醒来后的第一个物理动作")
        checkin.layout.addWidget(self.next_action)
        save = QPushButton("保存今日状态")
        save.setObjectName("mobilePrimary")
        save.clicked.connect(self._save_checkin)
        checkin.layout.addWidget(save)
        self.layout.addWidget(checkin)

        incident = Section("失控与恢复")
        add_incident = QPushButton("记录一次敌情（不扣经验）")
        add_incident.clicked.connect(self._add_incident)
        incident.layout.addWidget(add_incident)
        self.incident_layout = QVBoxLayout()
        incident.layout.addLayout(self.incident_layout)
        self.layout.addWidget(incident)
        self.layout.addStretch()

    def refresh(self) -> None:
        checkin = self.db.get_daily_checkin()
        idx = self.mode.findData(checkin.get("day_mode", "normal"))
        self.mode.setCurrentIndex(max(0, idx))
        self.energy.setValue(int(checkin.get("energy", 3)))
        self.mood.setValue(int(checkin.get("mood", 3)))
        self.sleep.setValue(int(checkin.get("sleep_recovery", 3)))
        self.meals.setChecked(bool(checkin.get("meals")))
        self.protein.setChecked(bool(checkin.get("protein")))
        self.produce.setChecked(bool(checkin.get("produce")))
        self.water.setChecked(bool(checkin.get("water")))
        self.next_action.setText(str(checkin.get("next_physical_action") or ""))
        clear_layout(self.incident_layout)
        incidents = self.db.get_incidents()
        if not incidents:
            label = QLabel("今天没有敌情报告。")
            label.setObjectName("mobileMuted")
            self.incident_layout.addWidget(label)
        for row in incidents:
            card = QFrame()
            card.setObjectName("mobileSubCard")
            layout = QVBoxLayout(card)
            text = QLabel(
                f"{row.get('application') or '失控模式'} · {row.get('duration_minutes', 0)} 分钟\n"
                f"环境：{row.get('trigger_environment') or '未记录'} · 情绪：{row.get('trigger_emotion') or '未记录'}"
            )
            text.setWordWrap(True)
            layout.addWidget(text)
            if row.get("recovered_at"):
                done = QLabel("已完成恢复：" + str(row.get("recovery_action") or "重新开始"))
                done.setObjectName("mobileSuccess")
                done.setWordWrap(True)
                layout.addWidget(done)
            else:
                button = QPushButton("完成 90 秒恢复协议")
                button.setObjectName("mobilePrimary")
                button.clicked.connect(lambda _=False, i=int(row["id"]): self._recover(i))
                layout.addWidget(button)
            self.incident_layout.addWidget(card)

    def _save_checkin(self) -> None:
        self.db.save_daily_checkin(
            day_mode=self.mode.currentData(),
            energy=self.energy.value(),
            mood=self.mood.value(),
            sleep_recovery=self.sleep.value(),
            meals=self.meals.isChecked(),
            protein=self.protein.isChecked(),
            produce=self.produce.isChecked(),
            water=self.water.isChecked(),
            next_physical_action=self.next_action.text().strip(),
        )
        info(self, "已保存", "今日模式与恢复状态已更新。")
        self.changed.emit()

    def _add_incident(self) -> None:
        dialog = IncidentDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.db.log_incident(**dialog.data())
        self.changed.emit()

    def _recover(self, incident_id: int) -> None:
        next_step, ok = QInputDialog.getText(self, "重新开始", "现在要做的最小物理动作：")
        if not ok:
            return
        result = self.db.complete_recovery(incident_id, "完成 90 秒恢复协议", next_step)
        info(self, "恢复成功", f"+{result.get('reward', 0)} 经验。真正的自主是更快停止下滑。")
        self.changed.emit()


class MorePage(ScrollPage):
    changed = Signal()

    def __init__(self, db: Database, data_dir: Path):
        super().__init__("更多世界", "角色、技能、首领、地图、周统计与存档。")
        self.db = db
        self.data_dir = data_dir
        self.sections: dict[str, Section] = {}
        self._build_sections()
        self.layout.addStretch()

    def _build_sections(self) -> None:
        character = Section("角色与属性")
        self.character_text = QLabel()
        self.character_text.setWordWrap(True)
        character.layout.addWidget(self.character_text)
        self.layout.addWidget(character)
        self.sections["character"] = character

        weekly = Section("最近 7 天")
        self.weekly_text = QLabel()
        self.weekly_text.setWordWrap(True)
        weekly.layout.addWidget(self.weekly_text)
        self.layout.addWidget(weekly)

        boss = Section("首领竞技场")
        self.boss_layout = QVBoxLayout()
        boss.layout.addLayout(self.boss_layout)
        self.layout.addWidget(boss)

        skills = Section("技能树")
        self.skills_layout = QVBoxLayout()
        skills.layout.addLayout(self.skills_layout)
        self.layout.addWidget(skills)

        world = Section("人生地图")
        self.world_layout = QVBoxLayout()
        world.layout.addLayout(self.world_layout)
        self.layout.addWidget(world)

        achievements = Section("成就")
        self.achievement_layout = QVBoxLayout()
        achievements.layout.addLayout(self.achievement_layout)
        self.layout.addWidget(achievements)

        save = Section("存档与身份")
        rename = QPushButton("修改玩家名称")
        rename.clicked.connect(self._rename)
        export = QPushButton("导出存档副本")
        export.clicked.connect(self._export_save)
        import_save = QPushButton("导入桌面版 earth.db")
        import_save.clicked.connect(self._import_save)
        save.layout.addWidget(rename)
        save.layout.addWidget(export)
        save.layout.addWidget(import_save)
        self.path_label = QLabel()
        self.path_label.setObjectName("mobileMuted")
        self.path_label.setWordWrap(True)
        save.layout.addWidget(self.path_label)
        self.layout.addWidget(save)

    def refresh(self) -> None:
        profile = self.db.get_character_profile()
        attrs = "\n".join(
            f"{item['name']} {item['score']}（{item['detail']}）"
            for item in profile.get("attribute_breakdown", [])
        )
        self.character_text.setText(
            f"{profile['name']} · {profile['title']}\n"
            f"{profile['class_name']} · 账号 {profile['account_level']} 级 · 金币 {profile['gold']}\n"
            f"属性总值 {profile.get('attribute_total', 0)}\n{attrs}"
        )
        weekly = self.db.get_weekly_stats(7)
        self.weekly_text.setText(
            f"记录 {weekly.get('total_minutes', 0)} 分钟 · 所有权 {weekly.get('ownership', 0)}%\n"
            f"获得 {weekly.get('total_exp', 0)} 经验 · {weekly.get('total_gold', 0)} 金币"
        )

        clear_layout(self.boss_layout)
        for boss in self.db.get_bosses():
            row = QFrame()
            row.setObjectName("mobileSubCard")
            lay = QVBoxLayout(row)
            lay.addWidget(QLabel(f"{boss['name']} · 生命 {boss['hp']} / {boss['max_hp']}"))
            detail = QLabel(f"弱点：{boss['weaknesses']}")
            detail.setWordWrap(True)
            detail.setObjectName("mobileMuted")
            lay.addWidget(detail)
            if not boss["is_active"]:
                select = QPushButton("设为当前首领")
                select.clicked.connect(lambda _=False, i=int(boss["id"]): self._select_boss(i))
                lay.addWidget(select)
            self.boss_layout.addWidget(row)

        clear_layout(self.skills_layout)
        for group in self.db.get_skills_grouped():
            unlocked = [s for s in group["skills"] if s.get("unlocked_at")]
            label = QLabel(
                f"{role_display(group['role_name'])} {group['role_level']} 级："
                + ("、".join(f"{s['skill_name']} Lv{s['skill_level']}" for s in unlocked) or "尚未觉醒")
            )
            label.setWordWrap(True)
            self.skills_layout.addWidget(label)

        clear_layout(self.world_layout)
        for region in self.db.get_world_map():
            nodes = region.get("nodes", [])
            completed = sum(1 for n in nodes if int(n.get("progress", 0)) >= int(n.get("target", 1)))
            label = QLabel(f"{region['title']}：{completed} / {len(nodes)} 节点完成")
            label.setWordWrap(True)
            self.world_layout.addWidget(label)

        clear_layout(self.achievement_layout)
        rows = self.db.get_achievements()
        for row in rows[:12]:
            mark = "✓" if row["completed_at"] else "○"
            label = QLabel(f"{mark} {row['title']} · {row['current_value']} / {row['target_value']}")
            label.setWordWrap(True)
            self.achievement_layout.addWidget(label)
        self.path_label.setText(f"手机内部存档：{self.db.path}")

    def _select_boss(self, boss_id: int) -> None:
        self.db.set_active_boss(boss_id)
        self.changed.emit()

    def _rename(self) -> None:
        current = self.db.get_player()["name"]
        name, ok = QInputDialog.getText(self, "修改玩家名称", "玩家名称：", text=current)
        if ok and name.strip():
            self.db.set_player_name(name.strip())
            self.changed.emit()

    def _export_save(self) -> None:
        suggested = str(self.data_dir / f"earth_mobile_{datetime.now():%Y%m%d_%H%M%S}.db")
        path, _ = QFileDialog.getSaveFileName(self, "导出存档", suggested, "SQLite 存档 (*.db)")
        if not path:
            return
        try:
            self.db.export_database(Path(path))
            info(self, "导出完成", path)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _import_save(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择桌面版 earth.db", "", "SQLite 存档 (*.db);;所有文件 (*)")
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "替换手机存档",
            "导入会先备份当前手机存档，然后用所选存档替换。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.import_database(Path(path), self.data_dir / "backup")
            info(self, "导入完成", "桌面存档已迁移到手机。")
            self.changed.emit()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ScrollPage(QScrollArea):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.layout = QVBoxLayout(self.body)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.layout.setContentsMargins(16, 18, 16, 24)
        self.layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("mobilePageTitle")
        heading.setWordWrap(True)
        self.layout.addWidget(heading)
        if subtitle:
            desc = QLabel(subtitle)
            desc.setObjectName("mobileMuted")
            desc.setWordWrap(True)
            self.layout.addWidget(desc)
        self.setWidget(self.body)


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("mobileCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        title = QLabel(label)
        title.setObjectName("mobileCardTitle")
        self.value = QLabel(value)
        self.value.setObjectName("mobileCardValue")
        self.value.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.value)

    def set_value(self, value: object) -> None:
        self.value.setText(str(value))


class Section(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("mobilePanel")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("mobileSectionTitle")
        heading.setWordWrap(True)
        self.layout.addWidget(heading)


class CompletionDialog(QDialog):
    def __init__(self, quest_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("完成现实行动")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        title = QLabel(quest_title)
        title.setObjectName("mobileDialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        layout.addWidget(QLabel("完成版本"))
        self.tier = QComboBox()
        self.tier.addItem("最低版：先开始并守住火种", "minimum")
        self.tier.addItem("标准版：完成一个行动块", "standard")
        self.tier.addItem("挑战版：完成行动并留下现实产物", "challenge")
        self.tier.setCurrentIndex(1)
        layout.addWidget(self.tier)

        layout.addWidget(QLabel("现实产物或失败记录"))
        self.output = QTextEdit()
        self.output.setPlaceholderText("例如：一页推导、文献卡片、代码结果；挑战版必须填写。")
        self.output.setMinimumHeight(96)
        layout.addWidget(self.output)

        layout.addWidget(QLabel("下一步物理动作"))
        self.next_step = QLineEdit()
        self.next_step.setPlaceholderText("例如：打开论文第 7 页")
        layout.addWidget(self.next_step)

        self.help_sought = QCheckBox("这次主动寻求了帮助")
        self.quality_cycle = QCheckBox("完成了工作—休息—返回循环")
        layout.addWidget(self.help_sought)
        layout.addWidget(self.quality_cycle)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("结算行动")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self.tier.currentData() == "challenge" and not self.output.toPlainText().strip():
            QMessageBox.warning(self, "需要现实产物", "挑战版必须填写现实产物或明确的失败记录。")
            return
        self.accept()

    def data(self) -> dict:
        return {
            "tier": self.tier.currentData(),
            "output_type": "移动端记录" if self.output.toPlainText().strip() else "",
            "output_text": self.output.toPlainText().strip(),
            "next_step": self.next_step.text().strip(),
            "help_sought": self.help_sought.isChecked(),
            "quality_cycle": self.quality_cycle.isChecked(),
        }


class SlotDialog(QDialog):
    STATUSES = (
        ("按计划完成", "planned_done"),
        ("主动调整", "intentional_change"),
        ("无意识失控", "unowned"),
        ("未记录 / 清空", "unrecorded"),
    )

    def __init__(self, label: str, record: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(label)
        layout = QVBoxLayout(self)
        heading = QLabel(label)
        heading.setObjectName("mobileDialogTitle")
        layout.addWidget(heading)
        layout.addWidget(QLabel("活动分类"))
        self.category = QLineEdit()
        self.category.setPlaceholderText("科研、阅读、运动、吃饭、休息……")
        layout.addWidget(self.category)
        layout.addWidget(QLabel("时间状态"))
        self.status = QComboBox()
        for text, code in self.STATUSES:
            self.status.addItem(text, code)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("备注 / 产出"))
        self.note = QTextEdit()
        self.note.setMinimumHeight(80)
        layout.addWidget(self.note)
        if record:
            self.category.setText(str(record.get("category") or ""))
            idx = self.status.findData(record.get("time_status") or "planned_done")
            self.status.setCurrentIndex(max(0, idx))
            self.note.setPlainText(str(record.get("note") or ""))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def data(self) -> dict:
        return {
            "category": self.category.text().strip(),
            "time_status": self.status.currentData(),
            "note": self.note.toPlainText().strip(),
        }


class IncidentDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("记录敌情")
        layout = QVBoxLayout(self)
        self.environment = QLineEdit()
        self.emotion = QLineEdit()
        self.application = QLineEdit()
        self.duration = QSpinBox()
        self.duration.setRange(1, 600)
        self.duration.setValue(30)
        self.note = QTextEdit()
        fields = (
            ("触发环境", self.environment),
            ("触发情绪", self.emotion),
            ("应用 / 失控模式", self.application),
            ("持续分钟", self.duration),
            ("备注", self.note),
        )
        for label, widget in fields:
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存敌情报告")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def data(self) -> dict:
        return {
            "trigger_environment": self.environment.text().strip(),
            "trigger_emotion": self.emotion.text().strip(),
            "application": self.application.text().strip(),
            "duration_minutes": self.duration.value(),
            "note": self.note.toPlainText().strip(),
        }

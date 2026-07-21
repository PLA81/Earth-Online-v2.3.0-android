from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QInputDialog, QMainWindow, QTabWidget

from database.connection import Database
from mobile_pages import HomePage, MorePage, RecoveryPage, TasksPage, TimelinePage

ROOT_DIR = Path(__file__).resolve().parent


def data_directory() -> Path:
    override = os.environ.get("EARTH_ONLINE_MOBILE_DATA_DIR")
    if override:
        path = Path(override)
    else:
        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        path = Path(location) if location else ROOT_DIR / "mobile_data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_style() -> str:
    path = ROOT_DIR / "assets" / "styles" / "mobile.qss"
    return path.read_text(encoding="utf-8") if path.exists() else ""


class MobileWindow(QMainWindow):
    def __init__(self, db: Database, data_dir: Path):
        super().__init__()
        self.db = db
        self.setWindowTitle("Earth Online v2.3.0 手机版")
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(True)
        self.home = HomePage(db)
        self.tasks = TasksPage(db)
        self.timeline = TimelinePage(db)
        self.recovery = RecoveryPage(db)
        self.more = MorePage(db, data_dir)
        self.pages = [self.home, self.tasks, self.timeline, self.recovery, self.more]
        self.tabs.addTab(self.home, "主页")
        self.tabs.addTab(self.tasks, "任务")
        self.tabs.addTab(self.timeline, "时间")
        self.tabs.addTab(self.recovery, "恢复")
        self.tabs.addTab(self.more, "更多")
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self._refresh_current)
        for page in self.pages:
            page.changed.connect(self.refresh_all)
        self.home.open_tasks.connect(lambda: self.tabs.setCurrentIndex(1))
        self.home.open_timeline.connect(lambda: self.tabs.setCurrentIndex(2))
        self._onboard()
        self.refresh_all()

    def _onboard(self) -> None:
        player = self.db.get_player()
        if player["name"] != "Player":
            return
        name, ok = QInputDialog.getText(self, "创建角色", "玩家名称：", text="地球玩家")
        if ok and name.strip():
            self.db.set_player_name(name.strip())

    def _refresh_current(self, index: int) -> None:
        page = self.pages[index]
        if hasattr(page, "refresh"):
            page.refresh()

    def refresh_all(self) -> None:
        for page in self.pages:
            page.refresh()


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Earth Online")
    app.setApplicationDisplayName("Earth Online")
    app.setApplicationVersion("2.3.0")
    app.setOrganizationName("EarthOnline")
    font = QFont()
    font.setFamilies(["Noto Sans CJK SC", "Microsoft YaHei UI", "sans-serif"])
    font.setPointSize(11)
    app.setFont(font)
    app.setStyleSheet(load_style())
    data_dir = data_directory()
    db = Database(data_dir / "earth.db")
    db.initialize()
    window = MobileWindow(db, data_dir)
    window.resize(420, 820)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path

from PySide6.QtWidgets import QApplication

from database.connection import Database
from mobile_pages import HomePage, MorePage, RecoveryPage, TasksPage, TimelinePage


def main() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path("mobile_test_data")
    root.mkdir(exist_ok=True)
    db = Database(root / "earth.db")
    db.initialize()
    pages = [HomePage(db), TasksPage(db), TimelinePage(db), RecoveryPage(db), MorePage(db, root)]
    for page in pages:
        page.resize(420, 820)
        page.show()
        page.refresh()
        app.processEvents()
    assert len(db.get_half_hour_records()) == 32
    assert len(db.get_character_profile()["attribute_breakdown"]) == 5
    print("mobile smoke test passed")


if __name__ == "__main__":
    main()

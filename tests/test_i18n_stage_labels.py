import pytest
from PySide6.QtWidgets import QApplication

import src.ui.main_window as main_window_module
from src.ui.main_window import DuplicateFinderApp
from src.utils.i18n import strings


class _DummyMessageBox:
    Question = 1
    AcceptRole = 2
    DestructiveRole = 3
    RejectRole = 4

    last_instance = None

    def __init__(self, *_args, **_kwargs):
        type(self).last_instance = self
        self.informative_text = ""
        self._clicked = None

    def setWindowTitle(self, *_args, **_kwargs):
        pass

    def setIcon(self, *_args, **_kwargs):
        pass

    def setText(self, *_args, **_kwargs):
        pass

    def setInformativeText(self, text):
        self.informative_text = str(text or "")

    def addButton(self, _text, role):
        btn = object()
        if role == self.RejectRole:
            self._clicked = btn
        return btn

    def setDefaultButton(self, *_args, **_kwargs):
        pass

    def exec(self):
        return 0

    def clickedButton(self):
        return self._clicked


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _setup_window(tmp_path, monkeypatch):
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))
    w = DuplicateFinderApp()
    try:
        w._scheduler_timer.stop()
    except Exception:
        pass
    return w


def test_stage_code_labels_follow_language_switch(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    prev_lang = getattr(type(strings), "current_lang", "ko")
    try:
        strings.set_language("ko")
        w._set_scan_stage_code("error")
        assert "오류" in w.lbl_scan_stage.text()
        w._set_scan_stage_code("abandoned")
        assert "중단됨" in w.lbl_scan_stage.text()

        strings.set_language("en")
        w._set_scan_stage_code("error")
        assert "Error" in w.lbl_scan_stage.text()
        w._set_scan_stage_code("abandoned")
        assert "Abandoned" in w.lbl_scan_stage.text()
    finally:
        strings.set_language(prev_lang)
        w.close()


def test_resume_dialog_stage_label_uses_i18n_keys(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    prev_lang = getattr(type(strings), "current_lang", "ko")
    try:
        strings.set_language("ko")
        monkeypatch.setattr(main_window_module, "QMessageBox", _DummyMessageBox)
        w._prompt_resume_session({"stage": "abandoned", "updated_at": None, "progress_message": ""})
        assert "중단됨" in _DummyMessageBox.last_instance.informative_text

        strings.set_language("en")
        w._prompt_resume_session({"stage": "error", "updated_at": None, "progress_message": ""})
        assert "Error" in _DummyMessageBox.last_instance.informative_text
    finally:
        strings.set_language(prev_lang)
        w.close()

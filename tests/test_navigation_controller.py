from types import SimpleNamespace

from src.ui.controllers.navigation_controller import NavigationController


class _DummyStack:
    def __init__(self):
        self.index = -1

    def setCurrentIndex(self, index):
        self.index = int(index)


class _DummyStatus:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = str(text or "")


class _DummyButton:
    def __init__(self, enabled=False):
        self._enabled = bool(enabled)

    def isEnabled(self):
        return self._enabled


class _DummyToast:
    def __init__(self):
        self.info_calls = []

    def info(self, msg, duration=0):
        self.info_calls.append((msg, duration))


class _DummySidebar:
    def __init__(self):
        self.page = None

    def set_page(self, page_name):
        self.page = str(page_name or "")


def _build_host(scanning=False):
    host = SimpleNamespace()
    host.page_stack = _DummyStack()
    host.status_label = _DummyStatus()
    host.btn_stop_scan = _DummyButton(enabled=scanning)
    host.toast_manager = _DummyToast()
    host.sidebar = _DummySidebar()
    host._tools_refresh_count = 0

    def _refresh_tools():
        host._tools_refresh_count += 1

    host.refresh_quarantine_list = _refresh_tools
    host.refresh_operations_list = _refresh_tools
    return host


def test_on_page_changed_tools_refreshes_lists_and_sets_page():
    c = NavigationController()
    host = _build_host(scanning=False)

    c.on_page_changed(host, "tools")

    assert host.page_stack.index == 2
    assert host._tools_refresh_count == 2
    assert host.status_label.text != ""
    assert len(host.toast_manager.info_calls) == 1


def test_on_page_changed_does_not_override_status_while_scanning():
    c = NavigationController()
    host = _build_host(scanning=True)
    host.status_label.text = "scanning..."

    c.on_page_changed(host, "results")

    assert host.page_stack.index == 1
    assert host.status_label.text == "scanning..."


def test_navigate_to_updates_sidebar_and_page():
    c = NavigationController()
    host = _build_host(scanning=False)

    c.navigate_to(host, "settings")

    assert host.sidebar.page == "settings"
    assert host.page_stack.index == 3

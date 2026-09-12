from pathlib import Path


def test_gui_wires_thread_safe_operator_inbox_into_runtime():
    source = Path("agents/blender_hub_gui.pyw").read_text(encoding="utf-8")
    assert "OperatorInboxBackend" in source
    assert "operator=self.operator" in source
    assert "self.operator.next_prompt()" in source
    assert "self.operator.answer(" in source
    assert "call_soon_threadsafe" in source


def test_gui_has_choice_buttons_and_free_text_reply():
    source = Path("agents/blender_hub_gui.pyw").read_text(encoding="utf-8")
    assert "ttk.Button" in source
    assert "ttk.Entry" in source
    assert "Send" in source


def test_default_windows_launcher_starts_gui_entrypoint():
    source = Path("agents/START_BLENDER_HUB.ps1").read_text(encoding="utf-8")
    assert "blender_hub_gui.pyw" in source

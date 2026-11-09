"""GUI smoke tests: build every dialog against a real Tk and make sure nothing raises.
Skipped when there is no display (run under `xvfb-run` on a headless Linux box, as CI does)."""
import os
import sys
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _build(root, make):
    dialog = make()
    root.update()
    assert dialog.winfo_exists()
    dialog.destroy()


def test_entry_dialog_new_and_edit_for_each_type(root):
    from cmdvault.data import _blank_entry
    from cmdvault.entry_dialog import EntryDialog
    from cmdvault import routine as rt
    _build(root, lambda: EntryDialog(root, ["Uncategorized"]))
    entry = _blank_entry("n", "echo hi")
    _build(root, lambda: EntryDialog(root, ["Uncategorized"], entry=entry))
    routine_entry = dict(entry, entry_type="routine", routine={"kind": "web", "steps": [rt.new_step("wait")]})
    _build(root, lambda: EntryDialog(root, ["Uncategorized"], entry=routine_entry))
    program_entry = dict(entry, entry_type="appimage", command="/bin/true")
    _build(root, lambda: EntryDialog(root, ["Uncategorized"], entry=program_entry))


def test_routine_and_step_dialogs(root):
    from cmdvault import routine as rt
    from cmdvault.routine_dialog import RoutineDialog, StepDialog
    for kind in ("web", "app"):
        steps = rt.get_templates()[kind][0][2]
        _build(root, lambda: RoutineDialog(root, "id1", "n", {"kind": kind, "steps": steps}))
    for step_type in rt.STEP_TYPES:
        _build(root, lambda: StepDialog(root, rt.new_step(step_type)))


def test_other_dialogs(root, tmp_path):
    from cmdvault import feedback as fb
    from cmdvault.automation_help_dialog import AutomationHelpDialog
    from cmdvault.bulk_dialog import BulkAddDialog
    from cmdvault.feedback_dialog import FeedbackDialog
    _build(root, lambda: FeedbackDialog(root, fb.FeedbackConfig("App", "1.0", "a@b.c", github_repo="o/r")))
    _build(root, lambda: AutomationHelpDialog(root))
    _build(root, lambda: BulkAddDialog(root, ["Uncategorized"]))


def test_dialogs_can_be_resized_and_keep_their_minimum(root):
    from cmdvault.entry_dialog import EntryDialog
    dialog = EntryDialog(root, ["Uncategorized"])
    root.update()
    min_w, min_h = dialog.minsize()
    assert min_w >= 300 and min_h >= 200
    dialog.geometry(f"{min_w + 120}x{min_h + 80}")
    root.update()
    assert dialog.winfo_width() >= min_w
    dialog.destroy()

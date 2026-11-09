"""Guards against a dialog method accidentally overriding a tkinter internal
(e.g. a method named _setup breaks Toplevel construction). Needs tkinter but no display."""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import (automation_help_dialog, bulk_dialog, entry_dialog, feedback_dialog, routine_dialog,
                      scrollframe, settings_dialog)

ALLOWED = {"__init__", "__module__", "__qualname__", "__doc__", "__dict__", "__weakref__", "destroy"}


def _tk_names(base):
    names = set()
    for klass in base.__mro__:
        names.update(vars(klass))
    return names


def test_no_dialog_overrides_tkinter_internals():
    checks = [(entry_dialog.EntryDialog, tk.Toplevel), (entry_dialog.EmojiPicker, tk.Toplevel),
              (entry_dialog.AppPicker, tk.Toplevel), (routine_dialog.RoutineDialog, tk.Toplevel),
              (routine_dialog.StepDialog, tk.Toplevel), (settings_dialog.SettingsDialog, tk.Toplevel),
              (feedback_dialog.FeedbackDialog, tk.Toplevel), (bulk_dialog.BulkAddDialog, tk.Toplevel),
              (automation_help_dialog.AutomationHelpDialog, tk.Toplevel),
              (scrollframe.ScrollableBody, tk.Frame), (scrollframe.CollapsibleSection, tk.Frame)]
    problems = []
    for cls, base in checks:
        # Python 3.13+ adds __firstlineno__/__static_attributes__ to every class; ignore dunders.
        own = {n for n in vars(cls) if not n.startswith("__")}
        clash = (own - ALLOWED) & _tk_names(base)
        if clash:
            problems.append((cls.__name__, sorted(clash)))
    assert not problems, problems

"""Silent-run tracking (running / Stop) and the lock that keeps crontab edits from overlapping."""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import scheduling as cv_sched
from cmdvault import terminals as cv_terminals

posix_only = pytest.mark.skipif(os.name == "nt", reason="uses sleep and process groups")


def _wait_for(cond, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


@posix_only
def test_silent_run_is_tracked_and_can_be_stopped():
    entry = {"id": "bg-test-1", "name": "Sleeper", "command": "sleep 30", "run_mode": "silent",
             "entry_type": "command", "admin_mode": "off"}
    messages = []
    cv_terminals.run_entry(entry, log=messages.append)
    try:
        assert cv_terminals.running_count("bg-test-1") == 1
        assert "bg-test-1" in cv_terminals.running_ids()
        assert cv_terminals.stop_entry("bg-test-1") == 1
        assert _wait_for(lambda: cv_terminals.running_count("bg-test-1") == 0)
        assert _wait_for(lambda: any("finished" in m for m in messages))
        assert "bg-test-1" not in cv_terminals.running_ids()
    finally:
        cv_terminals.stop_entry("bg-test-1")


@posix_only
def test_silent_run_that_finishes_is_forgotten_and_reports_exit_code():
    entry = {"id": "bg-test-2", "name": "Quick", "command": "echo hello; exit 3", "run_mode": "silent",
             "entry_type": "command", "admin_mode": "off"}
    messages = []
    cv_terminals.run_entry(entry, log=messages.append)
    assert _wait_for(lambda: any("exit code 3" in m for m in messages))
    assert any("hello" in m for m in messages)
    assert _wait_for(lambda: "bg-test-2" not in cv_terminals.running_ids())


def test_stop_entry_with_nothing_running_returns_zero():
    assert cv_terminals.stop_entry("never-started") == 0


def test_schedule_changes_do_not_overlap(monkeypatch):
    active, overlaps = [0], []

    def fake(entry, enabled):
        active[0] += 1
        if active[0] > 1:
            overlaps.append(True)
        time.sleep(0.05)
        active[0] -= 1
    monkeypatch.setattr(cv_sched, "_set_entry_schedule", fake)
    threads = [threading.Thread(target=cv_sched.set_entry_schedule, args=({"id": str(i)}, True)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not overlaps

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import schedule_spec as ss
from cmdvault import scheduling


def _entry(**kw):
    e = {"id": "abc", "schedule_enabled": True, "schedule_days": [], "schedule_time": "09:30"}
    e.update(kw)
    return e


def test_old_style_entry_still_makes_the_same_cron_line():
    assert scheduling._build_cron_schedule_line(_entry(), "/x/s.sh") == \
        '30 9 * * * bash "/x/s.sh" # command-vault-schedule:abc'
    line = scheduling._build_cron_schedule_line(_entry(schedule_days=["MO", "WE"]), "/x/s.sh")
    assert line.startswith("30 9 * * 1,3 ")


def test_multiple_times_make_one_cron_line_each():
    fields, error = ss.make_spec("times", "18:00, 8:15 12:00")
    assert error == "" and fields["schedule_times"] == ["08:15", "12:00", "18:00"] and fields["schedule_time"] == "08:15"
    lines = scheduling._build_cron_schedule_lines(_entry(**fields), "/x/s.sh")
    assert [l.split(" bash")[0] for l in lines] == ["15 8 * * *", "0 12 * * *", "0 18 * * *"]
    assert all("command-vault-schedule:abc" in l for l in lines)


def test_intervals_in_cron_and_task_scheduler():
    f, _ = ss.make_spec("interval", "", 15)
    assert ss.cron_schedules(_entry(**f)) == [("*/15", "*", "*")]
    f, _ = ss.make_spec("interval", "", 120, "08:00", "18:00")
    assert ss.cron_schedules(_entry(**f)) == [("0", "8-17/2", "*")]
    f, _ = ss.make_spec("interval", "", 30, "08:00", "18:00")
    e = _entry(schedule_days=["MO"], **f)
    assert ss.cron_schedules(e) == [("*/30", "8-17", "1")]
    assert ss.schtasks_jobs(e) == [("", ["/sc", "MINUTE", "/mo", "30", "/st", "08:00", "/et", "18:00"])]
    assert ss.summary(e) == "every 30 min 08:00-18:00"


def test_invalid_schedules_are_refused():
    for args in (("interval", "", 7), ("interval", "", 90), ("interval", "", 0), ("interval", "", "x"),
                 ("interval", "", 30, "08:00", ""), ("interval", "", 30, "18:00", "08:00"),
                 ("times", "25:00"), ("times", ""), ("times", "9am")):
        fields, error = ss.make_spec(*args)
        assert error and not fields, args


def test_windows_extra_times_become_extra_tasks():
    f, _ = ss.make_spec("times", "08:00, 20:00")
    cmds = scheduling._schtasks_create_commands(_entry(**f), "C:\\s.bat")
    names = [c[c.index("/tn") + 1] for c in cmds]
    assert names == ["CommandVault-abc", "CommandVault-abc-2"]
    assert cmds[1][-2:] == ["/st", "20:00"]


def test_sanitize_turns_broken_schedules_off():
    bad = ss.sanitize({"schedule_enabled": True, "schedule_mode": "interval", "schedule_interval": 7})
    assert bad["schedule_enabled"] is False
    ok = ss.sanitize({"schedule_enabled": True, "schedule_time": "07:05"})
    assert ok["schedule_enabled"] and ok["schedule_times"] == ["07:05"]

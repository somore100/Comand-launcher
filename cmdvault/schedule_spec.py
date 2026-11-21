"""schedule_spec -- what "run on a schedule" can mean, and how each kind becomes cron lines or
Task Scheduler commands. Pure logic (no tkinter, no subprocess) so it is easy to test.

An entry's schedule is described by these fields:
  schedule_enabled      on/off
  schedule_days         ["MO", ...]; empty = every day
  schedule_mode         "times"    at one or more fixed times each day (schedule_times)
                        "interval" repeat every schedule_interval minutes
  schedule_times        ["08:00", "13:30"] for "times" (schedule_time holds the first one)
  schedule_interval     minutes between runs for "interval"
  schedule_window_start / schedule_window_end
                        optional "HH:MM" limits for "interval" (e.g. only 08:00-18:00)

The OS schedulers' smallest step is one minute, so "every 30 seconds" is not possible. Cron
can only repeat on steps that divide evenly into the hour or day, so intervals are limited to
the lists below.
"""
import re

MODE_TIMES = "times"
MODE_INTERVAL = "interval"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MINUTE_STEPS = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30)
HOUR_STEPS = (1, 2, 3, 4, 6, 8, 12, 24)
MAX_TIMES = 24
WEEKDAY_CODES = {"SU": 0, "MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6}


def interval_help():
    return ("Every " + ", ".join(str(m) for m in MINUTE_STEPS) + " minutes, or every "
            + ", ".join(str(h) for h in HOUR_STEPS) + " hours")


def valid_interval(minutes):
    return minutes in MINUTE_STEPS or (minutes % 60 == 0 and minutes // 60 in HOUR_STEPS)


def parse_times(text):
    """'9:00, 13:30  18:00' -> (['09:00', '13:30', '18:00'], error)."""
    if isinstance(text, (list, tuple)):
        parts = [str(t) for t in text]
    else:
        parts = [p for p in re.split(r"[,\s;]+", str(text or "").strip()) if p]
    times = []
    for p in parts:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", p)
        if not m:
            return [], f"'{p}' is not a time. Use 24-hour HH:MM, e.g. 09:00 or 18:30."
        t = f"{int(m.group(1)):02d}:{m.group(2)}"
        if not TIME_RE.match(t):
            return [], f"'{p}' is not a valid time of day."
        if t not in times:
            times.append(t)
    if not times:
        return [], "Enter at least one time, e.g. 09:00."
    if len(times) > MAX_TIMES:
        return [], f"At most {MAX_TIMES} times per day."
    return sorted(times), ""


def make_spec(mode, times_text="", interval_minutes=0, window_start="", window_end=""):
    """Validates the pieces the dialog collects. Returns (fields, error); `fields` is the dict of
    schedule_* entry fields to store."""
    window_start, window_end = (window_start or "").strip(), (window_end or "").strip()
    if mode == MODE_INTERVAL:
        try:
            minutes = int(interval_minutes)
        except (TypeError, ValueError):
            return {}, "The repeat interval must be a whole number."
        if not valid_interval(minutes):
            return {}, f"That interval can't be scheduled evenly. Use: {interval_help()}."
        for w in (window_start, window_end):
            if w and not TIME_RE.match(w):
                return {}, "The 'only between' times must be 24-hour HH:MM, e.g. 08:00."
        if bool(window_start) != bool(window_end):
            return {}, "Fill in both 'only between' times, or leave both empty."
        if window_start and window_start >= window_end:
            return {}, "The 'only between' start must be earlier than the end (same day)."
        return {"schedule_mode": MODE_INTERVAL, "schedule_times": [], "schedule_interval": minutes,
                "schedule_window_start": window_start, "schedule_window_end": window_end,
                "schedule_time": window_start or "00:00"}, ""
    times, error = parse_times(times_text)
    if error:
        return {}, error
    return {"schedule_mode": MODE_TIMES, "schedule_times": times, "schedule_interval": 0,
            "schedule_window_start": "", "schedule_window_end": "", "schedule_time": times[0]}, ""


def sanitize(entry):
    """Makes an entry's schedule fields consistent (for vault load/import). Bad data turns the
    schedule off instead of raising."""
    entry.setdefault("schedule_mode", MODE_TIMES)
    entry.setdefault("schedule_times", [])
    entry.setdefault("schedule_interval", 0)
    entry.setdefault("schedule_window_start", "")
    entry.setdefault("schedule_window_end", "")
    mode = entry["schedule_mode"]
    if mode == MODE_INTERVAL:
        fields, error = make_spec(mode, "", entry["schedule_interval"], entry["schedule_window_start"],
                                  entry["schedule_window_end"])
    else:
        times = entry["schedule_times"] or ([entry.get("schedule_time")] if entry.get("schedule_time") else [])
        if not times:
            return entry  # nothing scheduled yet
        fields, error = make_spec(MODE_TIMES, times)
    if error:
        entry.update(schedule_mode=MODE_TIMES, schedule_times=[], schedule_interval=0, schedule_window_start="",
                     schedule_window_end="", schedule_time="", schedule_enabled=False)
    else:
        entry.update(fields)
    return entry


def entry_times(entry):
    if entry.get("schedule_mode") == MODE_INTERVAL:
        return []
    return list(entry.get("schedule_times") or ([entry["schedule_time"]] if entry.get("schedule_time") else []))


def summary(entry):
    """Short human description, e.g. '09:00', '08:00, 13:00', 'every 30 min', 'every 2 h 08:00-18:00'."""
    if entry.get("schedule_mode") == MODE_INTERVAL:
        n = int(entry.get("schedule_interval") or 0)
        text = f"every {n // 60} h" if n % 60 == 0 else f"every {n} min"
        if entry.get("schedule_window_start"):
            text += f" {entry['schedule_window_start']}-{entry['schedule_window_end']}"
        return text
    times = entry_times(entry)
    return ", ".join(times[:2]) + (f" +{len(times) - 2}" if len(times) > 2 else "")


def _dow(entry):
    days = entry.get("schedule_days") or []
    return ",".join(str(WEEKDAY_CODES[d]) for d in days) if days else "*"


def _hour_range(start, end):
    """Cron hour field covering an 'HH:MM'-'HH:MM' window (whole hours; the end hour is included only
    when the window ends past the top of the hour)."""
    h1, h2 = int(start[:2]), int(end[:2])
    if end[3:] == "00" and h2 > h1:
        h2 -= 1
    return h1, h2


def cron_schedules(entry):
    """[(minute, hour, dow), ...] cron fields for the entry; one item per cron line."""
    dow = _dow(entry)
    if entry.get("schedule_mode") == MODE_INTERVAL:
        n = int(entry["schedule_interval"])
        start, end = entry.get("schedule_window_start"), entry.get("schedule_window_end")
        if n < 60:
            hour = "*"
            if start:
                h1, h2 = _hour_range(start, end)
                hour = f"{h1}-{h2}"
            return [(f"*/{n}" if n > 1 else "*", hour, dow)]
        step = n // 60
        minute = str(int(start[3:])) if start else "0"
        if step == 24:
            return [(minute, str(int(start[:2])) if start else "0", dow)]
        if start:
            h1, h2 = _hour_range(start, end)
            hour = f"{h1}-{h2}/{step}" if step > 1 else f"{h1}-{h2}"
        else:
            hour = f"*/{step}" if step > 1 else "*"
        return [(minute, hour, dow)]
    return [(str(int(t[3:])), str(int(t[:2])), dow) for t in entry_times(entry)]


def schtasks_jobs(entry):
    """[(task_suffix, [schtasks schedule args...]), ...]: one scheduled task per item. The first has
    suffix '' (task name CommandVault-<id>); extra times get '-2', '-3'... Weekday filters apply to
    fixed times only: Task Scheduler can't combine them with a repeat interval from the command line."""
    days = entry.get("schedule_days") or []
    if entry.get("schedule_mode") == MODE_INTERVAL:
        n = int(entry["schedule_interval"])
        args = (["/sc", "MINUTE", "/mo", str(n)] if n < 60 else ["/sc", "HOURLY", "/mo", str(n // 60)])
        start, end = entry.get("schedule_window_start"), entry.get("schedule_window_end")
        args += ["/st", start or "00:00"]
        if end:
            args += ["/et", end]
        return [("", args)]
    jobs = []
    for i, t in enumerate(entry_times(entry)):
        args = (["/sc", "WEEKLY", "/d", ",".join(days)] if days else ["/sc", "DAILY"]) + ["/st", t]
        jobs.append(("" if i == 0 else f"-{i + 1}", args))
    return jobs

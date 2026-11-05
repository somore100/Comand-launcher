"""Unit tests for cmdvault.routine: step validation/description and the generated script's step runner."""
import importlib.util
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import routine as rt


def test_new_step_and_describe():
    step = rt.new_step("click")
    step["target"] = "Start"
    assert rt.describe_step(step) == "Click “Start”"
    step["on_fail"] = "retry"
    step["alt"] = "Start server"
    text = rt.describe_step(step)
    assert "Start server" in text and "retry 2" in text
    assert rt.describe_step({"type": "wait", "seconds": 5.0}) == "Wait 5 s"
    assert "optional" in rt.describe_step({"type": "press", "key": "Enter", "on_fail": "skip"})


def test_validation():
    assert rt.validate_steps([])
    assert rt.validate_step({"type": "goto", "url": "example.com"})
    assert rt.validate_step({"type": "goto", "url": "https://example.com"}) == ""
    assert rt.validate_step({"type": "click", "target": " "})
    assert rt.validate_step({"type": "wait", "seconds": "abc"})
    assert rt.validate_step({"type": "wait", "seconds": -1})
    assert rt.validate_step({"type": "fill", "target": "Email", "value": ""}) == ""  # empty text is allowed
    assert rt.validate_step({"type": "bogus"})
    assert "Step 2" in rt.validate_steps([rt.EXAMPLE_STEPS[0], {"type": "click", "target": ""}])


def _cvauto():
    from cmdvault.cvauto_source import SOURCE
    mod = types.ModuleType("cvauto")
    exec(compile(SOURCE, "cvauto.py", "exec"), mod.__dict__)
    mod.time = types.SimpleNamespace(sleep=lambda s: None, time=lambda: 0.0)
    return mod


class FakePage:
    def __init__(self, fail_for=()):
        self.fail_for, self.calls = set(fail_for), []

    def goto(self, url, timeout):
        self.calls.append(("goto", url))

    def locator(self, sel):
        self.last = sel
        return self

    @property
    def first(self):
        return self

    def get_by_role(self, *a, **k):
        return self

    def get_by_text(self, text, *a, **k):
        self.last = text
        return self

    def or_(self, other):
        return self

    def wait_for(self, state, timeout):
        if getattr(self, "last", None) in self.fail_for:
            raise RuntimeError("not found: " + self.last)

    def click(self, timeout):
        self.calls.append(("click", self.last))


def _web(cv, page):
    b = cv.Web()
    b.page = page
    return b


def test_web_goto_and_click():
    cv = _cvauto()
    page = FakePage()
    b = _web(cv, page)
    cv._web_step(b, {"type": "goto", "url": "https://x.test"})
    cv._web_step(b, {"type": "click", "target": "Start", "by": "text"})
    assert page.calls == [("goto", "https://x.test"), ("click", "Start")]


def test_web_alternative_target_is_tried():
    cv = _cvauto()
    page = FakePage(fail_for={"Start"})
    cv._web_step(_web(cv, page), {"type": "click", "target": "Start", "alt": "Start server", "by": "text"})
    assert page.calls == [("click", "Start server")]


def test_web_failure_raises_steperror_and_retry_repeats():
    cv = _cvauto()
    page = FakePage(fail_for={"Nope"})
    step = {"type": "click", "target": "Nope", "by": "text", "on_fail": "retry", "retries": 2}
    try:
        cv._web_step(_web(cv, page), step)
        assert False, "should have failed"
    except cv.StepError as e:
        assert "not found" in str(e)


def test_run_routine_skip_and_fail_exit_codes():
    cv = _cvauto()
    cv._app_step = lambda a, s: (_ for _ in ()).throw(cv.StepError("boom")) if s["type"] == "launch" else None
    steps = [{"type": "launch", "command": "x", "on_fail": "skip"}, {"type": "wait", "seconds": 0}]
    assert cv.run_routine(steps, kind="app") == 0
    steps[0]["on_fail"] = "stop"
    assert cv.run_routine(steps, kind="app") == 1


def test_script_embeds_name_safely_and_steps_roundtrip(tmp_path):
    src = rt.generate_script("abc", 'My "bot"', {"kind": "web", "show_browser": False,
                                                  "steps": [{"type": "fill", "target": "Email",
                                                             "value": "a'b\"c\\d", "by": "text"}]})
    compile(src, "generated.py", "exec")
    ns = {}
    # run only the STEPS assignment, not the import of cvauto / main call
    steps_line = next(l for l in src.splitlines() if l.startswith("STEPS ="))
    exec("import json\n" + steps_line, ns)
    assert ns["STEPS"][0]["value"] == "a'b\"c\\d" and ns["STEPS"][0]["desc"].startswith("Type")
    assert "show_browser=False" in src and "kind='web'" in src


def test_cvauto_source_compiles_and_lib_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "app_config_dir", lambda: str(tmp_path))
    path = rt.write_lib()
    assert os.path.isfile(path) and rt.write_lib() == path
    compile(open(path).read(), path, "exec")


def test_parse_keys_and_platform_keystrokes():
    cv = _cvauto()
    assert cv.parse_keys("ctrl+shift+t") == ({"ctrl", "shift"}, "t")
    assert cv.parse_keys("Return") == (set(), "Return")
    seen = []
    cv.app._ps = lambda script: seen.append(script) or ""
    cv.sys = types.SimpleNamespace(platform="win32")
    cv.app.keys("ctrl+shift+t")
    cv.app.keys("alt+F4")
    cv.app.type_text("a+b")
    assert "SendWait('^+t')" in seen[0] and "SendWait('%{F4}')" in seen[1] and "a{+}b" in seen[2]
    mac = []
    cv.app._osa = lambda script: mac.append(script) or ""
    cv.sys = types.SimpleNamespace(platform="darwin")
    cv.app.keys("cmd+t")
    cv.app.keys("Return")
    assert 'keystroke "t" using {command down}' in mac[0] and "key code 36" in mac[1]


def test_linux_app_calls_use_xdotool():
    cv = _cvauto()
    seen = []
    cv.sys = types.SimpleNamespace(platform="linux")
    cv.app._xdo = lambda *a: seen.append(a) or "42"
    cv.app.keys("ctrl+t")
    cv.app.focus("Firefox")
    assert seen == [("key", "--clearmodifiers", "ctrl+t"), ("search", "--onlyvisible", "--name", "Firefox"),
                    ("windowactivate", "--sync", "42")]


def test_routine_command_quotes_paths():
    cmd = rt.routine_command("abc")
    assert cmd.startswith('"') and cmd.endswith('abc.py"')


def test_all_templates_are_valid_and_generate_compilable_scripts():
    for kind, items in rt.get_templates().items():
        assert items
        for name, desc, steps in items:
            assert rt.validate_steps(steps) == "", name
            compile(rt.generate_script("id", name, {"kind": kind, "steps": steps}), name, "exec")


def test_recorded_steps_conversion():
    items = [{"type": "goto", "url": "https://a.test"},
             {"type": "click", "target": "Login", "by": "text"},
             {"type": "click", "target": "Login", "by": "text"},
             {"type": "fill", "target": "Email", "by": "text", "value": "x@y.z"},
             {"type": "fill", "target": "Password", "by": "text", "value": "", "note": "password"},
             {"type": "press", "key": "Enter"},
             {"type": "bogus"}]
    steps = rt.recorded_to_steps(items)
    assert [s["type"] for s in steps] == ["goto", "click", "fill", "fill", "press"]
    assert steps[3]["note"] == "password"
    assert rt.validate_steps(steps) == ""


def test_recorder_script_compiles():
    compile(rt._RECORDER, "recorder", "exec")



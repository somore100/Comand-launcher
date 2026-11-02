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


def _load_script(tmp_path, steps, show=True):
    src = rt.generate_script("abc", 'My "bot"', {"steps": steps, "show_browser": show})
    compile(src, "generated.py", "exec")
    path = tmp_path / "gen.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location("gen", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakePage:
    def __init__(self, fail_for=()):
        self.fail_for, self.calls = set(fail_for), []

    def goto(self, url, timeout):
        self.calls.append(("goto", url))

    def locator(self, sel):
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


def test_generated_script_runs_goto_and_click(tmp_path):
    mod = _load_script(tmp_path, [{"type": "goto", "url": "https://x.test"},
                                  {"type": "click", "target": "Start", "by": "text"}])
    page = FakePage()
    assert mod.run_step(page, mod.STEPS[0]) == (True, None)
    assert mod.run_step(page, mod.STEPS[1])[0] is True
    assert page.calls == [("goto", "https://x.test"), ("click", "Start")]


def test_alternative_target_is_tried(tmp_path):
    mod = _load_script(tmp_path, [{"type": "click", "target": "Start", "alt": "Start server", "by": "text"}])
    page = FakePage(fail_for={"Start"})
    ok, err = mod.run_step(page, mod.STEPS[0])
    assert ok and page.calls == [("click", "Start server")]


def test_failure_is_reported_and_retry_repeats(tmp_path, monkeypatch=None):
    mod = _load_script(tmp_path, [{"type": "click", "target": "Nope", "by": "text", "on_fail": "retry", "retries": 2}])
    mod.time = types.SimpleNamespace(sleep=lambda s: None)
    page = FakePage(fail_for={"Nope"})
    ok, err = mod.run_step(page, mod.STEPS[0])
    assert not ok and "not found" in str(err)


def test_script_embeds_name_safely_and_steps_roundtrip(tmp_path):
    mod = _load_script(tmp_path, [{"type": "fill", "target": "Email", "value": "a'b\"c\\d", "by": "text"}])
    assert mod.STEPS[0]["value"] == "a'b\"c\\d"
    assert mod.STEPS[0]["desc"].startswith("Type")


def test_routine_command_quotes_paths():
    cmd = rt.routine_command("abc")
    assert cmd.startswith('"') and cmd.endswith('abc.py"')

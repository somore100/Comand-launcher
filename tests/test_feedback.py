"""Unit tests for cmdvault.feedback (pure parts: validation, subject/body, mailto, relay)."""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import feedback as fb

CFG = fb.FeedbackConfig("Command Vault", "1.7.0", "support@example.com", "https://relay.test/x", "tok")


def test_validate():
    assert fb.validate("Bug Report", "Title", "A real description") == ""
    assert fb.validate("Bug Report", "abc", "A real description")      # title too short
    assert fb.validate("Bug Report", "Title", "short")                 # description too short
    assert fb.validate("Nope", "Title", "A real description")
    assert fb.validate("Bug Report", "  ", "A real description")
    assert fb.validate("Bug Report", "Title", "  ")
    assert fb.validate("Bug Report", "x" * 500, "d" * 20)
    assert fb.validate("Bug Report", "Title", "d" * 9000)


def test_subject_format():
    assert fb.build_subject(CFG, "Bug Report", "UI is  not\nworking") == "[Command Vault] [BUG] UI is not working"
    assert fb.build_subject(CFG, "Feature Suggestion", "x").startswith("[Command Vault] [FEATURE]")


def test_body_with_and_without_sysinfo():
    body = fb.build_body(CFG, "Bug Report", "T", "It broke", "Sam", [("CPU", "X"), ("RAM", "8 GB")])
    assert "App: Command Vault" in body and "Version: 1.7.0" in body and "From: Sam" in body
    assert "CPU: X" in body and "It broke" in body
    plain = fb.build_body(CFG, "Question", "T", "Q?")
    assert "not included by the user" in plain and "(not given)" in plain and "CPU" not in plain


def test_system_info_has_no_identifying_fields():
    labels = [k for k, _ in fb.collect_system_info("1.7.0")]
    assert labels == ["Operating system", "Architecture", "CPU", "GPU", "RAM", "App version", "Python"]


def test_mailto_roundtrip_and_truncation():
    url, cut = fb.build_mailto(CFG, "[A] [BUG] hi & bye", "line1\nline2")
    assert url.startswith("mailto:support@example.com?") and not cut
    qs = urllib.parse.parse_qs(url.split("?", 1)[1])
    assert qs["subject"] == ["[A] [BUG] hi & bye"] and qs["body"] == ["line1\nline2"]
    url, cut = fb.build_mailto(CFG, "s", "x" * 5000)
    assert cut and len(url) < 6000


class _Resp:
    def __init__(self, text): self.text = text
    def read(self, n): return self.text.encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_send_via_relay(monkeypatch):
    seen = {}
    def fake(req, timeout):
        seen["data"] = json.loads(req.data)
        return _Resp('{"ok": true}')
    monkeypatch.setattr(fb.urllib.request, "urlopen", fake)
    ok, _ = fb.send_via_relay(CFG, "s", "b")
    assert ok and seen["data"] == {"token": "tok", "subject": "s", "body": "b", "app": "Command Vault"}

    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda r, timeout: _Resp('{"ok": false, "error": "bad token"}'))
    ok, msg = fb.send_via_relay(CFG, "s", "b")
    assert not ok and "bad token" in msg

    monkeypatch.setattr(fb.urllib.request, "urlopen", lambda r, timeout: _Resp("<html>"))
    assert fb.send_via_relay(CFG, "s", "b")[0] is False

    def boom(r, timeout): raise fb.urllib.error.URLError("down")
    monkeypatch.setattr(fb.urllib.request, "urlopen", boom)
    assert fb.send_via_relay(CFG, "s", "b")[0] is False


def test_web_fallback_urls():
    url = fb.build_gmail_url(CFG, "[A] [BUG] x", "body & more")
    q = urllib.parse.parse_qs(url.split("?", 1)[1])
    assert url.startswith("https://mail.google.com/mail/?") and q["to"] == ["support@example.com"]
    assert q["su"] == ["[A] [BUG] x"] and q["body"] == ["body & more"]
    assert fb.build_github_issue_url(CFG, "s", "b") == ""
    cfg = fb.FeedbackConfig("A", "1", "s@e.com", github_repo="me/repo")
    gh = fb.build_github_issue_url(cfg, "[A] t", "x" * 9000)
    assert gh.startswith("https://github.com/me/repo/issues/new?") and len(gh) < 9000


def test_open_mailto_false_without_a_mail_client(monkeypatch):
    monkeypatch.setattr(fb, "has_mail_client", lambda: False)
    assert fb.open_mailto("mailto:x@y.z?subject=a") is False

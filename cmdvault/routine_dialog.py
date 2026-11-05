"""routine_dialog -- the no-code editor for web routines (see routine.py)."""
import copy
import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from . import routine as rt
from .scrollframe import ScrollableBody, fit_dialog
from .theme import (COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_PANEL, COLOR_RED, COLOR_SIDEBAR,
                    COLOR_SUBTEXT, COLOR_TEXT, FONT_HEADING, FONT_MONO, FONT_NORMAL, FONT_SMALL)

HELP = ("A routine is a list of steps that Command Vault does in a web browser, top to bottom: open a page, "
        "click a button, type something, wait. No code needed. Log in once with \"Test run\" and the browser "
        "remembers you for later runs, so no password goes into the routine.")


class StepDialog(tk.Toplevel):
    """Edit one step: what it does, plus what to do if it fails."""

    def __init__(self, master, step):
        super().__init__(master)
        self.result = None
        self.step = copy.deepcopy(step)
        spec = rt.STEP_TYPES[step["type"]]
        self.title(spec["label"])
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

        def lab(text):
            tk.Label(self, text=text, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w"
                     ).pack(anchor="w", padx=16, pady=(10, 2))

        def box(var, width=44):
            e = tk.Entry(self, textvariable=var, width=width, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                         insertbackground=COLOR_TEXT, relief="flat")
            e.pack(anchor="w", padx=16, ipady=3)
            return e

        tk.Label(self, text=spec["label"], bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(14, 0))

        self.vars = {}
        first = None
        for key, label, _kind, _default in spec["fields"]:
            lab(label)
            self.vars[key] = tk.StringVar(value=str(step.get(key, "")))
            e = box(self.vars[key])
            first = first or e

        self.by_var = tk.StringVar(value=rt.BY_CHOICES[step.get("by", "text")] if spec.get("uses_by") else "")
        if spec.get("uses_by"):
            lab("Find it by")
            ttk.Combobox(self, textvariable=self.by_var, values=list(rt.BY_CHOICES.values()),
                         state="readonly", width=30).pack(anchor="w", padx=16)

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(14, 0))
        lab("If this step fails")
        self.fail_var = tk.StringVar(value=rt.ON_FAIL_CHOICES[step.get("on_fail", "stop")])
        ttk.Combobox(self, textvariable=self.fail_var, values=list(rt.ON_FAIL_CHOICES.values()),
                     state="readonly", width=34).pack(anchor="w", padx=16)

        row = tk.Frame(self, bg=COLOR_BG)
        row.pack(anchor="w", padx=16, pady=(8, 0))
        self.retries_var = tk.StringVar(value=str(step.get("retries", 2)))
        self.timeout_var = tk.StringVar(value=str(step.get("timeout", 15)))
        tk.Label(row, text="Retries:", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(side="left")
        tk.Entry(row, textvariable=self.retries_var, width=4, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                 insertbackground=COLOR_TEXT, relief="flat").pack(side="left", padx=(4, 14))
        tk.Label(row, text="Give up after (seconds):", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL
                 ).pack(side="left")
        tk.Entry(row, textvariable=self.timeout_var, width=4, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                 insertbackground=COLOR_TEXT, relief="flat").pack(side="left", padx=(4, 0))

        self.alt_var = tk.StringVar(value=step.get("alt", ""))
        if spec.get("uses_alt"):
            lab("Alternative to try if the first isn't found (optional)")
            box(self.alt_var)
            tk.Label(self, text="e.g. the button might say \"Start\" or \"Start server\".", bg=COLOR_BG,
                     fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w", padx=16)

        bar = tk.Frame(self, bg=COLOR_BG)
        bar.pack(fill="x", padx=16, pady=14)
        tk.Button(bar, text="OK", command=self._ok, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4).pack(side="right")
        tk.Button(bar, text="Cancel", command=self.destroy, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(side="right", padx=(0, 8))
        if first:
            first.focus_set()
        fit_dialog(self, master)

    def _ok(self):
        step = copy.deepcopy(self.step)
        spec = rt.STEP_TYPES[step["type"]]
        for key, _label, kind, _d in spec["fields"]:
            raw = self.vars[key].get().strip() if key != "value" else self.vars[key].get()
            if kind == "number":
                try:
                    step[key] = float(raw)
                except ValueError:
                    messagebox.showwarning("Check the step", "Please enter a number.", parent=self)
                    return
            else:
                step[key] = raw
        if spec.get("uses_by"):
            step["by"] = next(k for k, v in rt.BY_CHOICES.items() if v == self.by_var.get())
        if spec.get("uses_alt"):
            step["alt"] = self.alt_var.get().strip()
        step["on_fail"] = next(k for k, v in rt.ON_FAIL_CHOICES.items() if v == self.fail_var.get())
        try:
            step["retries"] = max(0, int(self.retries_var.get()))
            step["timeout"] = max(1.0, float(self.timeout_var.get()))
        except ValueError:
            messagebox.showwarning("Check the step", "Retries and seconds must be numbers.", parent=self)
            return
        error = rt.validate_step(step)
        if error:
            messagebox.showwarning("Check the step", error, parent=self)
            return
        self.result = step
        self.destroy()


class RoutineDialog(tk.Toplevel):
    """The step list. `result` is {'steps': [...], 'show_browser': bool} on OK."""

    def __init__(self, master, entry_id, name, routine=None, profile_dir=None, start_recording=False):
        super().__init__(master)
        self.entry_id = entry_id
        self.profile_dir = profile_dir
        self.name = name or "routine"
        self.result = None
        routine = routine or {}
        self.steps = copy.deepcopy(routine.get("steps", []))
        self.kind = routine.get("kind", "web")
        self._busy = False
        self._rec_proc = None

        self.title("Edit steps")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

        scroll = ScrollableBody(self)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        tk.Label(body, text="Routine steps", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(body, text=HELP, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=460,
                 justify="left").pack(anchor="w", padx=16, pady=(4, 8))

        kind_row = tk.Frame(body, bg=COLOR_BG)
        kind_row.pack(anchor="w", padx=16, pady=(0, 6))
        tk.Label(kind_row, text="This routine controls:", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL
                 ).pack(side="left")
        self.kind_var = tk.StringVar(value=self.kind)
        for key, (label, _types) in rt.KINDS.items():
            tk.Radiobutton(kind_row, text=label, variable=self.kind_var, value=key, command=self._kind_changed,
                           bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                           activeforeground=COLOR_TEXT, font=FONT_SMALL).pack(side="left", padx=(8, 0))

        list_row = tk.Frame(body, bg=COLOR_BG)
        list_row.pack(fill="x", padx=16)
        self.listbox = tk.Listbox(list_row, height=9, width=58, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                                  selectbackground=COLOR_ACCENT_DIM, selectforeground=COLOR_TEXT, relief="flat",
                                  activestyle="none", exportselection=False)
        self.listbox.pack(side="left", fill="x", expand=True)
        self.listbox.bind("<Double-1>", lambda e: self._edit())
        side = tk.Frame(list_row, bg=COLOR_BG)
        side.pack(side="left", padx=(8, 0), anchor="n")
        for text, cmd, fg in (("Edit", self._edit, COLOR_TEXT), ("↑ Up", lambda: self._move(-1), COLOR_TEXT),
                              ("↓ Down", lambda: self._move(1), COLOR_TEXT),
                              ("Duplicate", self._duplicate, COLOR_TEXT), ("Delete", self._delete, COLOR_RED)):
            tk.Button(side, text=text, command=cmd, bg=COLOR_PANEL, fg=fg, relief="flat", font=FONT_SMALL,
                      width=9, pady=2).pack(pady=(0, 4))

        add_row = tk.Frame(body, bg=COLOR_BG)
        add_row.pack(anchor="w", padx=16, pady=(8, 0))
        tk.Label(add_row, text="Add a step:", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(side="left")
        self.add_var = tk.StringVar()
        self.add_box = ttk.Combobox(add_row, textvariable=self.add_var, state="readonly", width=28)
        self.add_box.pack(side="left", padx=6)
        self.add_box.bind("<<ComboboxSelected>>", self._add)
        self.record_btn = tk.Button(add_row, text="\u25CF Record", command=self._record, bg=COLOR_PANEL,
                                    fg=COLOR_RED, relief="flat", font=FONT_SMALL, padx=8)
        self.record_btn.pack(side="left", padx=(8, 0))

        tpl_row = tk.Frame(body, bg=COLOR_BG)
        tpl_row.pack(anchor="w", padx=16, pady=(6, 0))
        tk.Label(tpl_row, text="Or start from a template:", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL
                 ).pack(side="left")
        self.tpl_var = tk.StringVar()
        self.tpl_box = ttk.Combobox(tpl_row, textvariable=self.tpl_var, state="readonly", width=34)
        self.tpl_box.pack(side="left", padx=6)
        self.tpl_box.bind("<<ComboboxSelected>>", self._template)
        self.tpl_note = tk.Label(body, text="", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8),
                                 wraplength=460, justify="left")
        self.tpl_note.pack(anchor="w", padx=16, pady=(2, 0))

        self.show_var = tk.BooleanVar(value=routine.get("show_browser", True))
        self.show_check = tk.Checkbutton(body, text="Show the browser window while it runs (scheduled and boot runs are always hidden)",
                       variable=self.show_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                       activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                       )
        self.show_check.pack(anchor="w", padx=16, pady=(12, 0))

        self.sep = tk.Frame(body, bg=COLOR_PANEL, height=1)
        self.sep.pack(fill="x", padx=16, pady=(12, 8))
        self.setup_var = tk.StringVar()
        tk.Label(body, textvariable=self.setup_var, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=460, justify="left").pack(anchor="w", padx=16)
        btns = tk.Frame(body, bg=COLOR_BG)
        btns.pack(anchor="w", padx=16, pady=(6, 0))
        self.setup_row = btns
        self.setup_btn = tk.Button(btns, text="Set up browser automation", command=self._install_automation, bg=COLOR_PANEL,
                                   fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=3)
        self.setup_btn.pack(side="left")
        self.test_btn = tk.Button(btns, text="▶ Test run", command=self._test, bg=COLOR_ACCENT_DIM,
                                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=3)
        self.test_btn.pack(side="left", padx=(8, 0))
        self.log = tk.Text(body, height=7, width=62, font=FONT_MONO, bg=COLOR_PANEL, fg=COLOR_TEXT,
                           relief="flat", wrap="word", state="disabled")
        self.log.pack(anchor="w", padx=16, pady=(8, 14))

        bar = tk.Frame(scroll.footer, bg=COLOR_BG)
        bar.pack(fill="x", padx=16, pady=(6, 12))
        tk.Button(bar, text="Done", command=self._done, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4).pack(side="right")
        tk.Button(bar, text="Cancel", command=self._close, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(side="right", padx=(0, 8))

        self._kind_changed(initial=True)
        self._refresh()
        self._refresh_setup()
        fit_dialog(self, master)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())
        if start_recording:
            self.after(400, self._record)

    # -- kind / templates / recording ---------------------------------------
    def _types(self):
        return rt.KINDS[self.kind_var.get()][1]

    def _kind_changed(self, initial=False):
        new = self.kind_var.get()
        if not initial and new != self.kind and self.steps:
            if not messagebox.askyesno("Change type", "Steps for a website and for a desktop program are "
                                                      "different. Clear the current steps?", parent=self):
                self.kind_var.set(self.kind)
                return
            self.steps = []
        self.kind = new
        self.add_box.configure(values=[t["label"] for t in self._types().values()])
        self.tpl_box.configure(values=[n for n, _d, _s in rt.get_templates()[new]])
        self.tpl_note.configure(text="")
        web = new == "web"
        self.record_btn.configure(state="normal" if web else "disabled")
        if web:
            self.show_check.pack(anchor="w", padx=16, pady=(12, 0), before=self.sep)
        else:
            self.show_check.pack_forget()
        if not initial:
            self._refresh_setup()
            self._refresh()

    def _template(self, _event=None):
        name = self.tpl_var.get()
        self.tpl_var.set("")
        for tname, desc, steps in rt.get_templates()[self.kind]:
            if tname == name:
                if self.steps and not messagebox.askyesno("Replace steps", "Replace the current steps with this "
                                                                           "template?", parent=self):
                    return
                self.steps = copy.deepcopy(steps)
                self.tpl_note.configure(text=desc)
                self._refresh(select=0)
                return

    def _record(self):
        if self.kind != "web" and not self._rec_proc:
            return
        if self._rec_proc:
            self._rec_proc.terminate()
            return
        if self._busy:
            return
        if not rt.automation_python():
            messagebox.showinfo("Set up first", "Click \"Set up browser automation\" first (one time).", parent=self)
            return
        url = simpledialog.askstring("Record", "Which web address should the recording start on?",
                                     initialvalue="https://", parent=self)
        if not url or not url.lower().startswith(("http://", "https://")):
            return
        env = os.environ.copy()
        if self.profile_dir:
            os.makedirs(self.profile_dir, mode=0o700, exist_ok=True)
            env["COMMAND_VAULT_BROWSER_PROFILE"] = self.profile_dir
        try:
            self._rec_proc = subprocess.Popen([rt.automation_python(), "-u", rt.recorder_script_path(), url],
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        except OSError as e:
            messagebox.showerror("Couldn't record", str(e), parent=self)
            return
        self._set_busy(True)
        self.record_btn.configure(text="\u25A0 Stop recording", state="normal")
        self._say("Recording: do your routine in the browser that opened, then close it (or press Stop). "
                  "Password boxes are not recorded; log in once by hand instead.")
        proc = self._rec_proc

        def work():
            items = []
            for line in proc.stdout:
                line = line.strip()
                try:
                    item = json.loads(line)
                except ValueError:
                    if line:
                        self._say_threadsafe(line)
                    continue
                items.append(item)
                self._say_threadsafe("  + " + rt.describe_step(rt.recorded_to_steps([item])[0])
                                     if rt.recorded_to_steps([item]) else "")
            proc.wait()
            try:
                self.after(0, self._record_done, items)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _record_done(self, items):
        self._rec_proc = None
        self._set_busy(False)
        self.record_btn.configure(text="\u25CF Record")
        new_steps = rt.recorded_to_steps(items)
        if not new_steps:
            self._say("Nothing was recorded.")
            return
        sel = self._selected()
        at = sel + 1 if sel is not None else len(self.steps)
        self.steps[at:at] = new_steps
        self._refresh(select=at)
        self._say(f"Added {len(new_steps)} step(s). Check them, then use Test run.")
        if any(st.get("note") == "password" for st in new_steps):
            self._say("A password box was skipped: log in once with Test run and the browser remembers you.")

    def _close(self):
        if self._rec_proc:
            self._rec_proc.terminate()
        self.destroy()

    # -- list handling ------------------------------------------------------
    def _refresh(self, select=None):
        self.listbox.delete(0, "end")
        for i, step in enumerate(self.steps, 1):
            self.listbox.insert("end", f"{i}.  {rt.describe_step(step)}")
        if select is not None and self.steps:
            select = max(0, min(select, len(self.steps) - 1))
            self.listbox.selection_set(select)
            self.listbox.see(select)

    def _selected(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _add(self, _event=None):
        label = self.add_var.get()
        self.add_var.set("")
        step_type = next((k for k, v in self._types().items() if v["label"] == label), None)
        if not step_type:
            return
        dialog = StepDialog(self, rt.new_step(step_type))
        self.wait_window(dialog)
        if dialog.result:
            sel = self._selected()
            at = sel + 1 if sel is not None else len(self.steps)
            self.steps.insert(at, dialog.result)
            self._refresh(select=at)

    def _edit(self):
        i = self._selected()
        if i is None:
            return
        dialog = StepDialog(self, self.steps[i])
        self.wait_window(dialog)
        if dialog.result:
            self.steps[i] = dialog.result
            self._refresh(select=i)

    def _move(self, delta):
        i = self._selected()
        if i is None or not 0 <= i + delta < len(self.steps):
            return
        self.steps[i], self.steps[i + delta] = self.steps[i + delta], self.steps[i]
        self._refresh(select=i + delta)

    def _duplicate(self):
        i = self._selected()
        if i is not None:
            self.steps.insert(i + 1, copy.deepcopy(self.steps[i]))
            self._refresh(select=i + 1)

    def _delete(self):
        i = self._selected()
        if i is not None:
            del self.steps[i]
            self._refresh(select=i)

    # -- setup + test run ---------------------------------------------------
    def _refresh_setup(self):
        if self.kind_var.get() == "app":
            self.setup_var.set("Linux needs the 'xdotool' package (Fedora: sudo dnf install xdotool; Ubuntu/"
                               "Pop!_OS: sudo apt install xdotool) and an X11 session. macOS: allow Command Vault "
                               "under Privacy & Security > Accessibility. Windows needs nothing extra.")
            self.setup_btn.pack_forget()
            return
        self.setup_btn.pack(side="left", before=self.test_btn)
        if rt.automation_python():
            self.setup_var.set("Browser automation is set up. Routines use Playwright's own Chromium (separate from your "
                               "normal browser, with its own saved logins).")
            self.setup_btn.configure(text="Reinstall / update")
        else:
            self.setup_var.set("One-time setup needed: this downloads a private copy of Playwright and its own "
                               "Chromium browser (about 150 MB) into Command Vault's own folder. Routines use "
                               "that Chromium, not your normal Firefox/Chrome, and nothing else on your system "
                               "changes.")
            self.setup_btn.configure(text="Set up browser automation")

    def _say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip("\n") + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _say_threadsafe(self, text):
        try:
            self.after(0, self._say, text)
        except tk.TclError:
            pass

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.setup_btn.configure(state=state)
        self.test_btn.configure(state=state)

    def _install_automation(self):
        if self._busy:
            return
        self._set_busy(True)
        self._say("Setting up (this can take a few minutes)...")

        def work():
            ok, msg = rt.setup_automation(self._say_threadsafe)
            self.after(0, self._setup_done, ok, msg)

        threading.Thread(target=work, daemon=True).start()

    def _setup_done(self, ok, msg):
        self._set_busy(False)
        self._say(msg)
        self._refresh_setup()

    def _test(self):
        if self._busy:
            return
        error = rt.validate_steps(self.steps)
        if error:
            messagebox.showwarning("Check the steps", error, parent=self)
            return
        web = self.kind == "web"
        if web and not rt.automation_python():
            messagebox.showinfo("Set up first", "Click \"Set up browser automation\" first (one time).", parent=self)
            return
        routine = {"steps": self.steps, "show_browser": True, "kind": self.kind}
        path = rt.write_script(self.entry_id + "-test", self.name, routine)
        self._set_busy(True)
        self._say("--- Test run ---")

        def work():
            try:
                env = os.environ.copy()
                if self.profile_dir:
                    os.makedirs(self.profile_dir, mode=0o700, exist_ok=True)
                    env["COMMAND_VAULT_BROWSER_PROFILE"] = self.profile_dir
                proc = subprocess.Popen([rt.automation_python() or "python3", "-u", path], stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, env=env)
                for line in proc.stdout:
                    self._say_threadsafe(line)
                code = proc.wait()
            except OSError as e:
                self._say_threadsafe(f"Couldn't run: {e}")
                code = -1
            self.after(0, self._set_busy, False)
            self._say_threadsafe("--- Finished OK ---" if code == 0 else f"--- Stopped (exit code {code}) ---")

        threading.Thread(target=work, daemon=True).start()

    def _done(self):
        error = rt.validate_steps(self.steps)
        if error:
            messagebox.showwarning("Check the steps", error, parent=self)
            return
        self.result = {"steps": self.steps, "show_browser": bool(self.show_var.get()), "kind": self.kind}
        self.destroy()

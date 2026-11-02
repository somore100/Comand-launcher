"""routine_dialog -- the no-code editor for web routines (see routine.py)."""
import copy
import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
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
        if spec.get("uses_by"):
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

    def __init__(self, master, entry_id, name, routine=None, profile_dir=None):
        super().__init__(master)
        self.entry_id = entry_id
        self.profile_dir = profile_dir
        self.name = name or "routine"
        self.result = None
        routine = routine or {}
        self.steps = copy.deepcopy(routine.get("steps", []))
        self._busy = False

        self.title("Edit steps")
        self.configure(bg=COLOR_BG)
        self.resizable(False, True)
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
        add_box = ttk.Combobox(add_row, textvariable=self.add_var, state="readonly", width=30,
                               values=[s["label"] for s in rt.STEP_TYPES.values()])
        add_box.pack(side="left", padx=6)
        add_box.bind("<<ComboboxSelected>>", self._add)
        tk.Button(add_row, text="Start from an example", command=self._example, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(8, 0))

        self.show_var = tk.BooleanVar(value=routine.get("show_browser", True))
        tk.Checkbutton(body, text="Show the browser window while it runs (scheduled and boot runs are always hidden)",
                       variable=self.show_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                       activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                       ).pack(anchor="w", padx=16, pady=(12, 0))

        tk.Frame(body, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(12, 8))
        self.setup_var = tk.StringVar()
        tk.Label(body, textvariable=self.setup_var, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=460, justify="left").pack(anchor="w", padx=16)
        btns = tk.Frame(body, bg=COLOR_BG)
        btns.pack(anchor="w", padx=16, pady=(6, 0))
        self.setup_btn = tk.Button(btns, text="Set up browser automation", command=self._setup, bg=COLOR_PANEL,
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
        tk.Button(bar, text="Cancel", command=self.destroy, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(side="right", padx=(0, 8))

        self._refresh()
        self._refresh_setup()
        fit_dialog(self, master)

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
        step_type = next((k for k, v in rt.STEP_TYPES.items() if v["label"] == label), None)
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

    def _example(self):
        if self.steps and not messagebox.askyesno("Replace steps", "Replace the current steps with the example?",
                                                  parent=self):
            return
        self.steps = copy.deepcopy(rt.EXAMPLE_STEPS)
        self._refresh(select=0)

    # -- setup + test run ---------------------------------------------------
    def _refresh_setup(self):
        if rt.automation_python():
            self.setup_var.set("Browser automation is set up on this computer.")
            self.setup_btn.configure(text="Reinstall / update")
        else:
            self.setup_var.set("One-time setup needed: this downloads a private copy of Playwright and a browser "
                               "(about 150 MB) into Command Vault's own folder. Nothing else on your system changes.")
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

    def _setup(self):
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
        if not rt.automation_python():
            messagebox.showinfo("Set up first", "Click \"Set up browser automation\" first (one time).", parent=self)
            return
        routine = {"steps": self.steps, "show_browser": True}
        path = rt.write_script(self.entry_id + "-test", self.name, routine)
        self._set_busy(True)
        self._say("--- Test run (a browser window opens) ---")

        def work():
            try:
                env = os.environ.copy()
                if self.profile_dir:
                    os.makedirs(self.profile_dir, mode=0o700, exist_ok=True)
                    env["COMMAND_VAULT_BROWSER_PROFILE"] = self.profile_dir
                proc = subprocess.Popen([rt.automation_python(), "-u", path], stdout=subprocess.PIPE,
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
        self.result = {"steps": self.steps, "show_browser": bool(self.show_var.get())}
        self.destroy()

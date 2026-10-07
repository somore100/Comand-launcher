"""entry_dialog -- split out of the former monolithic main.py."""
from tkinter import filedialog
from tkinter import messagebox
import os
import re
import shutil
import tkinter as tk
from tkinter import ttk
import uuid
from .compat import HAVE_PYNPUT
from .apps import find_installed_apps
from .autostart import entry_autostart_enabled
from .browser import BROWSER_PROFILE_ENV, browser_profile_path
from .data import _load_config
from .hotkeys import HotkeyRecorderDialog
from .placeholders import extract_placeholders
from .platform_utils import is_linux, is_windows
from .scheduling import SCHEDULE_WEEKDAYS
from .theme import COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_PANEL, COLOR_RED, COLOR_SELECT, COLOR_SIDEBAR, COLOR_SUBTEXT, COLOR_TEXT, DEFAULT_ICON, EMOJI_CHOICES, FONT_HEADING, FONT_MONO, FONT_NORMAL, FONT_SMALL, SCHEDULE_TIME_RE, UNCATEGORIZED


# Emoji picker popup
# ---------------------------------------------------------------------------
class EmojiPicker(tk.Toplevel):
    def __init__(self, master, on_pick):
        super().__init__(master)
        self.title("Choose an icon")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cols = 8
        frame = tk.Frame(self, bg=COLOR_BG)
        frame.pack(padx=10, pady=10)
        for i, emoji in enumerate(EMOJI_CHOICES):
            r, c = divmod(i, cols)
            btn = tk.Button(frame, text=emoji, font=("Segoe UI", 16), width=2,
                             bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat",
                             command=lambda e=emoji: self._pick(e, on_pick))
            btn.grid(row=r, column=c, padx=2, pady=2)

        if is_windows():
            hint = "Tip: Win + . also opens Windows' built-in emoji panel here."
        else:
            hint = "Pick a symbol below to use as this entry's icon."
        tk.Label(self, text=hint, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=280, justify="left").pack(padx=10, pady=(0, 10), anchor="w")

    def _pick(self, emoji, callback):
        callback(emoji)
        self.destroy()


# ---------------------------------------------------------------------------
# Installed-app picker popup
# ---------------------------------------------------------------------------
class AppPicker(tk.Toplevel):
    def __init__(self, master, on_pick):
        super().__init__(master)
        self.title("Pick Installed App")
        self.configure(bg=COLOR_BG)
        self.geometry("420x420")
        self.transient(master)
        self.grab_set()

        self.on_pick = on_pick
        self.all_apps = find_installed_apps()

        tk.Label(self, text="Pick Installed App", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=14, pady=(14, 4))

        if not self.all_apps:
            msg = ("No installed apps were found to scan on this system."
                   if (is_linux() or is_windows())
                   else "App scanning isn't supported on this OS yet.")
            tk.Label(self, text=msg, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                     wraplength=380, justify="left").pack(padx=14, pady=10, anchor="w")
            tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                      relief="flat", padx=12, pady=4).pack(pady=10)
            return

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh())
        search_entry = tk.Entry(self, textvariable=self.search_var, font=FONT_NORMAL, bg=COLOR_PANEL,
                                 fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        search_entry.pack(fill="x", padx=14, pady=(0, 8), ipady=5)
        search_entry.focus_set()

        list_frame = tk.Frame(self, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=14)
        self.listbox = tk.Listbox(list_frame, bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat",
                                   selectbackground=COLOR_SELECT, font=FONT_NORMAL, activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-1>", lambda e: self._confirm())

        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=14, pady=10)
        tk.Button(btn_frame, text="Cancel", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=12, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Use Selected", command=self._confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", padx=12, pady=4, font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 8))

        self._filtered = []
        self._refresh()

    def _refresh(self):
        query = self.search_var.get().strip().lower()
        self.listbox.delete(0, tk.END)
        self._filtered = [a for a in self.all_apps if query in a[0].lower()] if query else self.all_apps
        for name, _, _ in self._filtered:
            self.listbox.insert(tk.END, name)

    def _confirm(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name, command, _ = self._filtered[sel[0]]
        self.on_pick(name, command)
        self.destroy()


class InsertPlaceholderDialog(tk.Toplevel):
    """Small dialog for naming an input box before inserting {{name}} (or
    {{name:default}}) at the cursor in the command box."""
    def __init__(self, master, suggested_name):
        super().__init__(master)
        self.result = None
        self.title("Add Input Box")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        tk.Label(self, text="Name", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w"
                  ).pack(fill="x", padx=16, pady=(16, 0))
        self.name_var = tk.StringVar(value=suggested_name)
        name_entry = tk.Entry(self, textvariable=self.name_var, width=32, font=FONT_NORMAL, bg=COLOR_PANEL,
                               fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        name_entry.pack(fill="x", padx=16, pady=(2, 8))
        name_entry.bind("<Return>", lambda e: self._confirm())

        tk.Label(self, text="Default value (optional)", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                  anchor="w").pack(fill="x", padx=16)
        self.default_var = tk.StringVar()
        default_entry = tk.Entry(self, textvariable=self.default_var, width=32, font=FONT_NORMAL,
                                  bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        default_entry.pack(fill="x", padx=16, pady=(2, 12))
        default_entry.bind("<Return>", lambda e: self._confirm())

        btns = tk.Frame(self, bg=COLOR_BG)
        btns.pack(fill="x", padx=16, pady=(0, 16))
        tk.Button(btns, text="Cancel", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=12, pady=4).pack(side="right")
        tk.Button(btns, text="Insert", command=self._confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4).pack(side="right", padx=(0, 8))

        name_entry.focus_set()
        name_entry.select_range(0, tk.END)

    def _confirm(self):
        name = self.name_var.get().strip()
        if not re.fullmatch(r"\w+", name or ""):
            messagebox.showwarning("Invalid name", "Use letters, numbers, and underscores only (no spaces).")
            return
        self.result = (name, self.default_var.get().strip())
        self.destroy()


# ---------------------------------------------------------------------------
# Add / Edit dialog
# ---------------------------------------------------------------------------
class EntryDialog(tk.Toplevel):
    def __init__(self, master, categories, entry=None):
        super().__init__(master)
        self.result = None
        self.categories = categories
        self.entry = entry

        self.title("Edit Entry" if entry else "Add Entry")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        pad = {"padx": 16, "pady": (10, 0)}

        def label(text):
            return tk.Label(self, text=text, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w")

        # Name + icon row
        label("Icon").grid(row=0, column=0, sticky="w", **pad)
        label("Name").grid(row=0, column=1, sticky="w", **pad)

        self.icon_var = tk.StringVar(value=entry["icon"] if entry else DEFAULT_ICON)
        self.name_var = tk.StringVar(value=entry["name"] if entry else "")

        icon_row = tk.Frame(self, bg=COLOR_BG)
        icon_row.grid(row=1, column=0, sticky="w", padx=(16, 6))
        self.icon_label = tk.Label(icon_row, textvariable=self.icon_var, font=("Segoe UI", 16),
                                    bg=COLOR_PANEL, fg=COLOR_TEXT, width=2)
        self.icon_label.pack(side="left")
        tk.Button(icon_row, text="\U0001F600", font=("Segoe UI", 10), command=self._open_emoji_picker,
                  bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat", width=2).pack(side="left", padx=(4, 0))

        name_entry = tk.Entry(self, textvariable=self.name_var, width=32, font=FONT_NORMAL,
                               bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        name_entry.grid(row=1, column=1, sticky="we", padx=(0, 16))

        # Type
        self.type_var = tk.StringVar(value=entry["entry_type"] if entry else "command")
        label("Type").grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        type_frame = tk.Frame(self, bg=COLOR_BG)
        type_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=16)
        tk.Radiobutton(type_frame, text="Command / Script", variable=self.type_var, value="command",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL, command=self._sync_command_widget
                        ).pack(side="left")
        tk.Radiobutton(type_frame, text="AppImage", variable=self.type_var, value="appimage",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL, command=self._sync_command_widget
                        ).pack(side="left", padx=(12, 0))
        tk.Button(type_frame, text="Pick Installed App", command=self._open_app_picker,
                  bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8
                  ).pack(side="left", padx=(16, 0))

        # Command (multiline text box)
        self.path_label_var = tk.StringVar(value="Command (supports multiple lines)")
        tk.Label(self, textvariable=self.path_label_var, bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL, anchor="w").grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(10, 0))

        cmd_frame = tk.Frame(self, bg=COLOR_BG)
        cmd_frame.grid(row=5, column=0, columnspan=2, sticky="we", padx=16)
        self.command_text = tk.Text(cmd_frame, width=46, height=6, font=FONT_MONO, bg=COLOR_PANEL,
                                     fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat", wrap="none",
                                     undo=True)
        self.command_text.pack(side="left", fill="both", expand=True)
        cmd_scroll = ttk.Scrollbar(cmd_frame, orient="vertical", command=self.command_text.yview)
        self.command_text.configure(yscrollcommand=cmd_scroll.set)
        cmd_scroll.pack(side="left", fill="y")
        if entry:
            self.command_text.insert("1.0", entry["command"])

        cfg = _load_config()
        self._placeholder_shortcut = cfg.get("insert_placeholder_tkbind", "<Control-i>")
        self._placeholder_shortcut_display = cfg.get("insert_placeholder_display", "Ctrl+I")
        self.command_text.bind(self._placeholder_shortcut, self._add_input_box_event)

        browse_frame = tk.Frame(self, bg=COLOR_BG)
        browse_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))
        tk.Button(browse_frame, text="Browse for file...", command=self._browse_command, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8).pack(side="left")
        tk.Button(browse_frame, text="+ Add Input Box", command=self._add_input_box, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))
        tk.Label(browse_frame, text=".sh / .bat / .ps1 / .py files auto-run with the right interpreter",
                  bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))

        tk.Label(self, text=f"Tip: type {{{{name}}}} or {{{{name:default}}}} yourself, click \"+ Add Input Box\", "
                             f"or press {self._placeholder_shortcut_display} in the command box \u2014 all three "
                             f"prompt for a value each time you run this (e.g. git commit -m \"{{{{message:update}}}}\")",
                  bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=420, justify="left"
                  ).grid(row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))

        # Working directory
        label("Working Directory (optional)").grid(row=8, column=0, columnspan=2, sticky="w", **pad)
        wd_frame = tk.Frame(self, bg=COLOR_BG)
        wd_frame.grid(row=9, column=0, columnspan=2, sticky="we", padx=16)
        self.wd_var = tk.StringVar(value=entry["working_dir"] if entry else "")
        tk.Entry(wd_frame, textvariable=self.wd_var, width=38, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  insertbackground=COLOR_TEXT, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(wd_frame, text="Browse", command=self._browse_dir, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT,
                  relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))

        # Category
        label("Category").grid(row=10, column=0, columnspan=2, sticky="w", **pad)
        self.category_var = tk.StringVar(value=entry["category"] if entry else (categories[0] if categories else UNCATEGORIZED))
        cat_values = categories if categories else [UNCATEGORIZED]
        self.category_combo = ttk.Combobox(self, textvariable=self.category_var, values=cat_values, width=34,
                                            font=FONT_NORMAL)
        self.category_combo.grid(row=11, column=0, columnspan=2, sticky="we", padx=16)

        # Run mode
        label("Run Mode").grid(row=12, column=0, columnspan=2, sticky="w", **pad)
        self.mode_var = tk.StringVar(value=entry["run_mode"] if entry else "terminal")
        mode_frame = tk.Frame(self, bg=COLOR_BG)
        mode_frame.grid(row=13, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 4))
        tk.Radiobutton(mode_frame, text="Open in Terminal", variable=self.mode_var, value="terminal",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL).pack(side="left")
        tk.Radiobutton(mode_frame, text="Run Silently (no window)", variable=self.mode_var, value="silent",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL).pack(side="left", padx=(12, 0))

        # Autostart
        self.autostart_var = tk.BooleanVar(
            value=entry_autostart_enabled(entry["id"]) if entry else False
        )
        autostart_frame = tk.Frame(self, bg=COLOR_BG)
        autostart_frame.grid(row=14, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 10))
        tk.Checkbutton(autostart_frame, text="Run this automatically when the computer starts",
                        variable=self.autostart_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                        ).pack(anchor="w")
        tk.Label(autostart_frame,
                 text="Runs on its own via the OS startup mechanism \u2014 works even if Command Vault isn't set to autostart.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                 ).pack(anchor="w")

        # Scheduled run (daily, or on chosen weekdays, at a specific time)
        self.schedule_enabled_var = tk.BooleanVar(
            value=entry.get("schedule_enabled", False) if entry else False
        )
        self.schedule_time_var = tk.StringVar(
            value=(entry.get("schedule_time") or "09:00") if entry else "09:00"
        )
        existing_days = set(entry.get("schedule_days") or []) if entry else set()
        self.schedule_day_vars = {d: tk.BooleanVar(value=(d in existing_days)) for d in SCHEDULE_WEEKDAYS}

        schedule_frame = tk.Frame(self, bg=COLOR_BG)
        schedule_frame.grid(row=15, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 10))
        tk.Checkbutton(schedule_frame, text="Run on a schedule", variable=self.schedule_enabled_var,
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL).pack(anchor="w")

        time_row = tk.Frame(schedule_frame, bg=COLOR_BG)
        time_row.pack(anchor="w", pady=(2, 0))
        tk.Label(time_row, text="Time (24h):", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(side="left")
        tk.Entry(time_row, textvariable=self.schedule_time_var, width=6, font=FONT_NORMAL, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat").pack(side="left", padx=(6, 0))

        days_row = tk.Frame(schedule_frame, bg=COLOR_BG)
        days_row.pack(anchor="w", pady=(4, 0))
        for d in SCHEDULE_WEEKDAYS:
            tk.Checkbutton(days_row, text=d, variable=self.schedule_day_vars[d], bg=COLOR_BG, fg=COLOR_TEXT,
                            selectcolor=COLOR_PANEL, activebackground=COLOR_BG, activeforeground=COLOR_TEXT,
                            font=("Segoe UI", 8)).pack(side="left")

        tk.Label(schedule_frame,
                 text="Leave all days unchecked to run every day. Runs via the OS scheduler \u2014 works even "
                      "if Command Vault isn't open \u2014 and always runs silently in the background, "
                      "regardless of Run Mode above (there's no terminal to open at an unattended run).",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                 ).pack(anchor="w", pady=(4, 0))

        # Persistent browser profile (for Playwright/Selenium bot scripts)
        self.browser_profile_var = tk.BooleanVar(
            value=bool(entry.get("browser_profile", False)) if entry else False
        )
        self.browser_profile_dir_var = tk.StringVar(
            value=entry.get("browser_profile_dir", "") if entry else ""
        )
        bp_frame = tk.Frame(self, bg=COLOR_BG)
        bp_frame.grid(row=16, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 10))
        tk.Checkbutton(bp_frame, text="Persistent browser profile (for browser-automation bots)",
                        variable=self.browser_profile_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                        ).pack(anchor="w")
        bp_row = tk.Frame(bp_frame, bg=COLOR_BG)
        bp_row.pack(anchor="w", fill="x", pady=(2, 0))
        tk.Label(bp_row, text="Folder:", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(side="left")
        tk.Entry(bp_row, textvariable=self.browser_profile_dir_var, width=30, font=FONT_NORMAL, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat").pack(side="left", padx=(6, 0))
        tk.Button(bp_row, text="Browse", command=self._browse_browser_profile, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT,
                  relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))
        tk.Button(bp_row, text="Reset", command=self._reset_browser_profile, bg=COLOR_PANEL, fg=COLOR_RED,
                  relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))
        tk.Label(bp_frame,
                 text=f"Leave the folder blank for an automatic one. Your script gets its path in the "
                      f"{BROWSER_PROFILE_ENV} environment variable \u2014 pass it to Playwright's "
                      f"launch_persistent_context() to stay logged in between runs. The folder holds login "
                      f"cookies, so treat it like a password. Reset deletes it (logs the bot out).",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                 ).pack(anchor="w", pady=(4, 0))

        # Launch shortcut (optional, needs pynput)
        self.entry_hotkey_pynput = entry.get("hotkey_pynput", "") if entry else ""
        self.entry_hotkey_display_var = tk.StringVar(
            value=(entry.get("hotkey_display") or "Not set") if entry else "Not set"
        )
        if HAVE_PYNPUT:
            hotkey_frame = tk.Frame(self, bg=COLOR_BG)
            hotkey_frame.grid(row=17, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))
            tk.Label(hotkey_frame, text="Launch Shortcut (optional)", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                     font=FONT_SMALL, anchor="w").pack(anchor="w")
            row = tk.Frame(hotkey_frame, bg=COLOR_BG)
            row.pack(anchor="w", pady=(2, 0))
            tk.Label(row, textvariable=self.entry_hotkey_display_var, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                     font=("Segoe UI", 10, "bold"), padx=8, pady=3).pack(side="left")
            tk.Button(row, text="Record...", command=self._record_entry_hotkey, bg=COLOR_ACCENT_DIM,
                      fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8, pady=3).pack(side="left", padx=(6, 0))
            tk.Button(row, text="Clear", command=self._clear_entry_hotkey, bg=COLOR_PANEL, fg=COLOR_RED,
                      relief="flat", font=FONT_SMALL, padx=8, pady=3).pack(side="left", padx=(6, 0))
            tk.Label(hotkey_frame, text="Runs this specific command from anywhere, even with Command Vault "
                                         "closed \u2014 needs an X11 session on Linux.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                     ).pack(anchor="w", pady=(2, 0))
            buttons_row = 18
        else:
            buttons_row = 17

        # Buttons
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.grid(row=buttons_row, column=0, columnspan=2, sticky="we", padx=16, pady=(6, 16))
        tk.Button(btn_frame, text="Cancel", command=self._cancel, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", font=FONT_NORMAL, padx=14, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Save", command=self._save, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=14, pady=4).pack(side="right", padx=(0, 8))

        self._sync_command_widget()
        name_entry.focus_set()

    def _record_entry_hotkey(self):
        dialog = HotkeyRecorderDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        display_string, pynput_string, _tk_bind_string = dialog.result

        conflicts = self.master._all_used_hotkeys(exclude_pynput=self.entry_hotkey_pynput or None)
        if pynput_string in conflicts:
            messagebox.showwarning("Already in use", f"{display_string} is already assigned to "
                                                        f"{conflicts[pynput_string]}. Pick a different combo.")
            return

        self.entry_hotkey_pynput = pynput_string
        self.entry_hotkey_display_var.set(display_string)

    def _clear_entry_hotkey(self):
        self.entry_hotkey_pynput = ""
        self.entry_hotkey_display_var.set("Not set")

    def _sync_command_widget(self):
        if self.type_var.get() == "appimage":
            self.path_label_var.set("AppImage path")
        else:
            self.path_label_var.set("Command (supports multiple lines)")

    def _open_emoji_picker(self):
        EmojiPicker(self, self._set_icon)

    def _set_icon(self, emoji):
        self.icon_var.set(emoji)

    def _open_app_picker(self):
        AppPicker(self, self._apply_picked_app)

    def _apply_picked_app(self, name, command):
        if not self.name_var.get().strip():
            self.name_var.set(name)
        self.command_text.delete("1.0", tk.END)
        self.command_text.insert("1.0", command)
        self.type_var.set("command")
        self.mode_var.set("silent")
        self._sync_command_widget()

    def _browse_command(self):
        path = filedialog.askopenfilename(title="Select script or AppImage")
        if path:
            self.command_text.delete("1.0", tk.END)
            self.command_text.insert("1.0", path)
            if path.lower().endswith(".appimage"):
                self.type_var.set("appimage")
                self._sync_command_widget()

    def _add_input_box_event(self, event=None):
        self._add_input_box()
        return "break"

    def _add_input_box(self):
        existing_names = {n for n, _ in extract_placeholders(self.command_text.get("1.0", "end-1c"))}
        suggested = "value"
        i = 2
        while suggested in existing_names:
            suggested = f"value{i}"
            i += 1

        dialog = InsertPlaceholderDialog(self, suggested)
        self.wait_window(dialog)
        if not dialog.result:
            return
        name, default = dialog.result
        token = "{{" + name + "}}" if not default else "{{" + name + ":" + default + "}}"
        self.command_text.insert(tk.INSERT, token)
        self.command_text.focus_set()

    def _browse_dir(self):
        path = filedialog.askdirectory(title="Select working directory")
        if path:
            self.wd_var.set(path)

    def _browse_browser_profile(self):
        path = filedialog.askdirectory(title="Select browser profile folder")
        if path:
            self.browser_profile_dir_var.set(path)

    def _reset_browser_profile(self):
        """Deletes this entry's profile folder (all saved logins). Uses the
        values currently in the dialog, so it works before Save too."""
        probe = {
            "id": self.entry["id"] if self.entry else "",
            "browser_profile": True,
            "browser_profile_dir": self.browser_profile_dir_var.get(),
        }
        if not probe["id"] and not probe["browser_profile_dir"].strip():
            messagebox.showinfo("Browser profile", "Nothing to reset yet \u2014 save this entry first.")
            return
        path = browser_profile_path(probe)
        if not os.path.isdir(path):
            messagebox.showinfo("Browser profile", "No saved profile exists yet.")
            return
        if not messagebox.askyesno(
                "Reset browser profile",
                f"Delete everything in this folder?\n\n{path}\n\nThe bot will have to log in again.",
                parent=self):
            return
        try:
            shutil.rmtree(path)
        except OSError as e:
            messagebox.showerror("Couldn't reset profile", str(e), parent=self)

    def _cancel(self):
        self.result = None
        self.destroy()

    def _save(self):
        name = self.name_var.get().strip()
        command = self.command_text.get("1.0", "end-1c").strip("\n")
        if not name or not command.strip():
            messagebox.showwarning("Missing info", "Name and Command/Path are both required.")
            return
        category = self.category_var.get().strip() or UNCATEGORIZED
        icon = self.icon_var.get().strip() or DEFAULT_ICON

        schedule_enabled = bool(self.schedule_enabled_var.get())
        schedule_time = self.schedule_time_var.get().strip()
        if schedule_enabled and not SCHEDULE_TIME_RE.match(schedule_time):
            messagebox.showwarning(
                "Invalid time",
                "Schedule time must be in 24-hour HH:MM format, e.g. 09:00 or 18:30."
            )
            return
        schedule_days = [d for d in SCHEDULE_WEEKDAYS if self.schedule_day_vars[d].get()]

        self.result = {
            "id": self.entry["id"] if self.entry else str(uuid.uuid4()),
            "name": name,
            "command": command,
            "working_dir": self.wd_var.get().strip(),
            "run_mode": self.mode_var.get(),
            "entry_type": self.type_var.get(),
            "category": category,
            "icon": icon,
            "autostart": bool(self.autostart_var.get()),
            "hotkey_display": self.entry_hotkey_display_var.get() if self.entry_hotkey_pynput else "",
            "hotkey_pynput": self.entry_hotkey_pynput,
            "schedule_enabled": schedule_enabled,
            "schedule_days": schedule_days,
            "schedule_time": schedule_time,
            "browser_profile": bool(self.browser_profile_var.get()),
            "browser_profile_dir": self.browser_profile_dir_var.get().strip(),
        }
        self.destroy()


# ---------------------------------------------------------------------------

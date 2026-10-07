"""app -- split out of the former monolithic main.py."""
from datetime import datetime
from tkinter import messagebox
import os
import queue
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk
from .compat import pynput_keyboard, HAVE_PYNPUT, HAVE_PIL, pystray, HAVE_PYSTRAY
from .autostart import set_entry_autostart
from .browser import browser_profile_path
from .config import APP_VERSION
from .data import _load_config, _save_config, load_data, save_data
from .entry_dialog import EntryDialog
from .hotkeys import build_tray_image
from .instance import acquire_single_instance_lock, release_single_instance_lock
from .placeholders import extract_placeholders
from .platform_utils import is_mac, is_windows
from .scheduling import set_entry_schedule
from .settings_dialog import SettingsDialog
from .terminals import run_entry
from .theme import ALL_CATEGORY, COLOR_ACCENT, COLOR_BG, COLOR_GREEN, COLOR_PANEL, COLOR_RED, COLOR_ROW_ALT, COLOR_SELECT, COLOR_SIDEBAR, COLOR_SUBTEXT, COLOR_TEXT, COLOR_YELLOW, DEFAULT_ICON, FONT_HEADING, FONT_NORMAL, FONT_SMALL, FONT_TITLE, UNCATEGORIZED
from .updates import check_for_update


# Main application
# ---------------------------------------------------------------------------
class CommandVault(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Command Vault")
        self.geometry("860x680")
        self.minsize(700, 520)
        self.configure(bg=COLOR_BG)
        self._set_window_icon()

        self.data = load_data()
        self.selected_category = ALL_CATEGORY
        self._log_queue = queue.Queue()
        self._main_thread_queue = queue.Queue()
        self._hotkey_listener = None
        self._tray_icon = None
        self._instance_lock_handle = acquire_single_instance_lock(
            lambda: self._post_to_main_thread(self._show_window)
        )

        self._build_style()
        self._build_layout()
        self._refresh_categories()
        self._refresh_list()
        self.after(150, self._drain_log_queue)
        self._log("Command Vault ready.")

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._rebuild_hotkey_listener()
        self._check_for_update_startup()

    # -- global hotkey / background mode ------------------------------------
    def _rebuild_hotkey_listener(self, retry_count=0):
        """Rebuilds the single combined GlobalHotKeys listener from the
        app-level hotkey (config.json) plus every entry's own hotkey
        (commands.json). Call this after any hotkey is added/changed/removed.

        retry_count > 0 means this call is itself a retry: registration can
        fail right at login/autostart if the X session isn't fully up yet,
        so failures here back off and try again a few times rather than
        giving up silently."""
        if not HAVE_PYNPUT:
            return
        self._stop_hotkey_listener()

        mapping = {}
        cfg = _load_config()
        app_hotkey = cfg.get("hotkey_pynput")
        if app_hotkey:
            mapping[app_hotkey] = self._on_app_hotkey_triggered

        for entry in self.data.get("commands", []):
            hk = entry.get("hotkey_pynput")
            if hk and hk not in mapping:
                mapping[hk] = self._make_entry_hotkey_callback(entry["id"])

        if not mapping:
            return

        try:
            self._hotkey_listener = pynput_keyboard.GlobalHotKeys(mapping)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            # GlobalHotKeys() and .start() succeed synchronously even when
            # the underlying X connection is broken -- that failure happens
            # *inside* the listener's background thread (e.g. X session not
            # ready yet at login), which then dies silently with no
            # exception we can catch here. So verify shortly after that the
            # thread is actually still alive before declaring success.
            self.after(500, lambda: self._verify_hotkey_listener(retry_count))
        except Exception as e:
            self._hotkey_listener = None
            self._schedule_hotkey_retry(retry_count, e)

    def _verify_hotkey_listener(self, retry_count):
        listener = self._hotkey_listener
        if listener is None:
            return  # already replaced or cleared by something else since
        if not listener.is_alive():
            self._hotkey_listener = None
            self._schedule_hotkey_retry(retry_count, "listener thread died (X session likely wasn't ready)")
        elif retry_count > 0:
            self._log("Global hotkeys registered successfully.")

    def _schedule_hotkey_retry(self, retry_count, error):
        max_retries = 5
        if retry_count < max_retries:
            delay_ms = min(2000 * (retry_count + 1), 10000)
            self._log(f"Hotkey registration failed (attempt {retry_count + 1}/{max_retries}), "
                      f"retrying in {delay_ms // 1000}s: {error}")
            self.after(delay_ms, lambda: self._rebuild_hotkey_listener(retry_count + 1))
        else:
            self._log(f"Couldn't register global hotkey(s) after {max_retries} attempts: {error}")

    def _make_entry_hotkey_callback(self, entry_id):
        def callback():
            self._post_to_main_thread(lambda: self._run_entry_by_id(entry_id))
        return callback

    def _run_entry_by_id(self, entry_id):
        for entry in self.data.get("commands", []):
            if entry["id"] == entry_id:
                run_entry(entry, log=self._log)
                return

    def _all_used_hotkeys(self, exclude_pynput=None):
        """Returns {pynput_string: description} across the app-level hotkey
        and every entry's hotkey, for conflict checking. exclude_pynput lets
        the thing currently being edited not conflict with its own old value."""
        used = {}
        cfg = _load_config()
        app_hotkey = cfg.get("hotkey_pynput")
        if app_hotkey and app_hotkey != exclude_pynput:
            used[app_hotkey] = f"App: Show Command Vault ({cfg.get('hotkey_display', '')})"
        for entry in self.data.get("commands", []):
            hk = entry.get("hotkey_pynput")
            if hk and hk != exclude_pynput:
                used[hk] = f'"{entry["name"]}" ({entry.get("hotkey_display", "")})'
        return used

    def _on_app_hotkey_triggered(self):
        self._post_to_main_thread(self._show_window)

    def _stop_hotkey_listener(self):
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    def _post_to_main_thread(self, fn):
        self._main_thread_queue.put(fn)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _set_window_icon(self):
        """Sets the titlebar/taskbar icon from the same baked-in logo the
        tray icon uses. Best-effort: some platforms/WMs ignore iconphoto,
        and PIL might not be present, so failures here are silent."""
        if not HAVE_PIL:
            return
        try:
            from PIL import ImageTk
            self._window_icon_ref = ImageTk.PhotoImage(build_tray_image(64))
            self.iconphoto(True, self._window_icon_ref)
        except Exception:
            pass

    def _check_for_update_startup(self):
        def _on_found(tag, html_url):
            self._post_to_main_thread(lambda: self._notify_update_available(tag, html_url))
        check_for_update(force=False, on_result=_on_found)

    def _notify_update_available(self, tag, html_url):
        # Don't nag about the same version more than once per run/day --
        # once shown, remember it so it doesn't reappear tomorrow's cooldown
        # cycle unless a newer tag shows up.
        cfg = _load_config()
        if cfg.get("dismissed_update_version") == tag:
            return
        self._log(f"Update available: {tag} (you have v{APP_VERSION}) -- {html_url}")
        if messagebox.askyesno(
                "Update available",
                f"Command Vault {tag} is available (you have v{APP_VERSION}).\n\n"
                f"Open the release page?"):
            self._open_url(html_url)
        cfg["dismissed_update_version"] = tag
        _save_config(cfg)

    @staticmethod
    def _open_url(url):
        try:
            if is_windows():
                os.startfile(url)
            elif is_mac():
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        except OSError:
            pass

    def _ensure_tray_icon(self):
        if self._tray_icon:
            return True
        if not HAVE_PYSTRAY:
            return False
        try:
            image = build_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("Show Command Vault", lambda: self._post_to_main_thread(self._show_window),
                                  default=True),
                pystray.MenuItem("Quit", lambda: self._post_to_main_thread(self._quit_app)),
            )
            self._tray_icon = pystray.Icon("command-vault", image, "Command Vault", menu)
            self._tray_icon.run_detached()
            return True
        except Exception as e:
            self._tray_icon = None
            self._log(f"Tray icon unavailable ({e})")
            return False

    def _stop_tray_icon(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _on_close_request(self):
        cfg = _load_config()
        if not cfg.get("hotkey_pynput"):
            self._quit_app()
            return
        if self._ensure_tray_icon():
            self.withdraw()
            self._log("Minimized to tray \u2014 press your hotkey or use the tray icon to reopen.")
        else:
            self.iconify()
            self._log("Minimized \u2014 press your hotkey or restore from the taskbar to reopen.")

    def _quit_app(self):
        self._stop_hotkey_listener()
        self._stop_tray_icon()
        release_single_instance_lock(self._instance_lock_handle)
        self._instance_lock_handle = None
        self.destroy()

    # -- styling -----------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                         background=COLOR_PANEL,
                         fieldbackground=COLOR_PANEL,
                         foreground=COLOR_TEXT,
                         rowheight=30,
                         borderwidth=0,
                         font=FONT_NORMAL)
        style.configure("Treeview.Heading",
                         background=COLOR_SIDEBAR,
                         foreground=COLOR_SUBTEXT,
                         font=FONT_HEADING,
                         borderwidth=0)
        style.map("Treeview",
                  background=[("selected", COLOR_SELECT)],
                  foreground=[("selected", COLOR_TEXT)])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # -- layout --------------------------------------------------------------
    def _build_layout(self):
        sidebar = tk.Frame(self, bg=COLOR_SIDEBAR, width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Command Vault", bg=COLOR_SIDEBAR, fg=COLOR_TEXT, font=FONT_TITLE,
                 anchor="w", justify="left", wraplength=170).pack(fill="x", padx=16, pady=(20, 16))

        tk.Label(sidebar, text="CATEGORIES", bg=COLOR_SIDEBAR, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 anchor="w").pack(fill="x", padx=16)

        self.category_frame = tk.Frame(sidebar, bg=COLOR_SIDEBAR)
        self.category_frame.pack(fill="both", expand=True, padx=8, pady=(6, 8))

        tk.Button(sidebar, text="+ New Category", command=self._add_category, bg=COLOR_SIDEBAR,
                  fg=COLOR_ACCENT, relief="flat", font=FONT_SMALL, anchor="w", padx=8
                  ).pack(fill="x", padx=8, pady=(0, 4))

        tk.Button(sidebar, text="\u2699 Settings", command=self._open_settings, bg=COLOR_SIDEBAR,
                  fg=COLOR_SUBTEXT, relief="flat", font=FONT_SMALL, anchor="w", padx=8
                  ).pack(fill="x", padx=8, pady=(0, 16), side="bottom")

        main = tk.Frame(self, bg=COLOR_BG)
        main.pack(side="left", fill="both", expand=True)

        top_bar = tk.Frame(main, bg=COLOR_BG)
        top_bar.pack(fill="x", padx=20, pady=(20, 10))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        search_entry = tk.Entry(top_bar, textvariable=self.search_var, font=FONT_NORMAL, bg=COLOR_PANEL,
                                 fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        search_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
        self._set_placeholder(search_entry, "Search commands...")

        tk.Button(top_bar, text="+ Add", command=self._add_entry, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4).pack(side="left")

        list_frame = tk.Frame(main, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        columns = ("icon", "name", "category", "mode", "boot", "schedule")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("icon", text="")
        self.tree.heading("name", text="Name")
        self.tree.heading("category", text="Category")
        self.tree.heading("mode", text="Mode")
        self.tree.heading("boot", text="Boot")
        self.tree.heading("schedule", text="Sched")
        self.tree.column("icon", width=40, anchor="center", stretch=False)
        self.tree.column("name", width=300, anchor="w")
        self.tree.column("category", width=130, anchor="w")
        self.tree.column("mode", width=130, anchor="center")
        self.tree.column("boot", width=50, anchor="center", stretch=False)
        self.tree.column("schedule", width=70, anchor="center", stretch=False)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._run_selected())

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.tree.tag_configure("odd", background=COLOR_PANEL)
        self.tree.tag_configure("even", background=COLOR_ROW_ALT)

        action_bar = tk.Frame(main, bg=COLOR_BG)
        action_bar.pack(fill="x", padx=20, pady=(0, 10))

        tk.Button(action_bar, text="\u25B6 Run", command=self._run_selected, bg=COLOR_GREEN, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=6).pack(side="left")
        self.run_all_button = tk.Button(action_bar, text="\u25B6\u25B6 Run All", command=self._run_visible,
                                         bg=COLOR_YELLOW, fg=COLOR_SIDEBAR, font=("Segoe UI", 10, "bold"),
                                         relief="flat", padx=16, pady=6)
        self.run_all_button.pack(side="left", padx=(8, 0))
        tk.Button(action_bar, text="Edit", command=self._edit_selected, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=FONT_NORMAL, relief="flat", padx=16, pady=6).pack(side="left", padx=(8, 0))
        tk.Button(action_bar, text="Delete", command=self._delete_selected, bg=COLOR_PANEL, fg=COLOR_RED,
                  font=FONT_NORMAL, relief="flat", padx=16, pady=6).pack(side="left", padx=(8, 0))

        # Console panel: shows exactly what ran and its live output, so
        # silent-mode entries (which show no window) aren't a black box.
        console_header = tk.Frame(main, bg=COLOR_BG)
        console_header.pack(fill="x", padx=20)
        tk.Label(console_header, text="CONSOLE", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 anchor="w").pack(side="left")
        tk.Button(console_header, text="Clear", command=self._clear_console, bg=COLOR_BG, fg=COLOR_SUBTEXT,
                  relief="flat", font=FONT_SMALL, padx=6).pack(side="right")

        console_frame = tk.Frame(main, bg=COLOR_PANEL, height=150)
        console_frame.pack(fill="x", padx=20, pady=(4, 20))
        console_frame.pack_propagate(False)

        self.console_text = tk.Text(console_frame, bg=COLOR_PANEL, fg=COLOR_TEXT,
                                     font=("Consolas", 9) if is_windows() else ("DejaVu Sans Mono", 9),
                                     relief="flat", wrap="word", state="disabled", padx=8, pady=6)
        self.console_text.pack(side="left", fill="both", expand=True)
        console_scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=console_scroll.set)
        console_scroll.pack(side="right", fill="y")

    def _clear_console(self):
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", tk.END)
        self.console_text.configure(state="disabled")

    def _log(self, message):
        """Thread-safe: worker threads (reading silent-mode process output)
        call this too -- it only queues; the widget update happens on the
        main thread via _drain_log_queue."""
        self._log_queue.put(message)

    def _drain_log_queue(self):
        try:
            while True:
                message = self._log_queue.get_nowait()
                self._append_console(message)
        except queue.Empty:
            pass
        try:
            while True:
                fn = self._main_thread_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.after(150, self._drain_log_queue)

    def _append_console(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_text.configure(state="normal")
        self.console_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.console_text.see(tk.END)
        self.console_text.configure(state="disabled")

    def _set_placeholder(self, entry, text):
        entry.insert(0, text)
        entry.config(fg=COLOR_SUBTEXT)

        def on_focus_in(_):
            if entry.get() == text:
                entry.delete(0, tk.END)
                entry.config(fg=COLOR_TEXT)

        def on_focus_out(_):
            if not entry.get():
                entry.insert(0, text)
                entry.config(fg=COLOR_SUBTEXT)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def _open_settings(self):
        SettingsDialog(self)

    # -- category sidebar ----------------------------------------------------
    def _refresh_categories(self):
        for widget in self.category_frame.winfo_children():
            widget.destroy()

        used = sorted({c["category"] for c in self.data["commands"]} | set(self.data["categories"]))
        all_cats = [ALL_CATEGORY] + used

        for cat in all_cats:
            is_selected = cat == self.selected_category
            btn = tk.Button(
                self.category_frame,
                text=cat,
                anchor="w",
                bg=COLOR_SELECT if is_selected else COLOR_SIDEBAR,
                fg=COLOR_ACCENT if is_selected else COLOR_TEXT,
                relief="flat",
                font=FONT_NORMAL,
                padx=10,
                pady=6,
                command=lambda c=cat: self._select_category(c),
            )
            btn.pack(fill="x", pady=1)

    def _select_category(self, cat):
        self.selected_category = cat
        self._refresh_categories()
        self._refresh_list()

    def _add_category(self):
        top = tk.Toplevel(self, bg=COLOR_BG)
        top.title("New Category")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="Category name", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL
                 ).pack(padx=16, pady=(16, 4), anchor="w")
        var = tk.StringVar()
        entry = tk.Entry(top, textvariable=var, width=30, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                          insertbackground=COLOR_TEXT, relief="flat")
        entry.pack(padx=16, fill="x")
        entry.focus_set()

        def confirm():
            name = var.get().strip()
            if name and name not in self.data["categories"]:
                self.data["categories"].append(name)
                save_data(self.data)
                self._refresh_categories()
            top.destroy()

        btn_frame = tk.Frame(top, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=16)
        tk.Button(btn_frame, text="Cancel", command=top.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=12, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Add", command=confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", padx=12, pady=4, font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", lambda e: confirm())

    # -- list ------------------------------------------------------------
    def _visible_commands(self):
        query = self.search_var.get().strip().lower()
        if query == "search commands...":
            query = ""
        result = []
        for cmd in self.data["commands"]:
            if self.selected_category != ALL_CATEGORY and cmd["category"] != self.selected_category:
                continue
            if query and query not in cmd["name"].lower() and query not in cmd["command"].lower():
                continue
            result.append(cmd)
        return result

    @staticmethod
    def _command_preview(cmd):
        lines = cmd["command"].splitlines()
        if not lines:
            return ""
        first = lines[0]
        return first + " \u2026" if len(lines) > 1 else first

    def _refresh_list(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        visible = self._visible_commands()
        for i, cmd in enumerate(visible):
            mode_label = "Silent" if cmd.get("run_mode") == "silent" else "Terminal"
            if cmd.get("entry_type") == "appimage":
                mode_label += " \u00b7 AppImage"
            boot_label = "\u2713" if cmd.get("autostart") else ""
            schedule_label = cmd.get("schedule_time", "") if cmd.get("schedule_enabled") else ""
            tag = "even" if i % 2 else "odd"
            self.tree.insert("", tk.END, iid=cmd["id"],
                              values=(cmd.get("icon", DEFAULT_ICON), cmd["name"], cmd["category"], mode_label,
                                      boot_label, schedule_label),
                              tags=(tag,))
        self._update_run_all_label(len(visible))

    def _update_run_all_label(self, count):
        if not hasattr(self, "run_all_button"):
            return
        if self.selected_category == ALL_CATEGORY:
            label = f"\u25B6\u25B6 Run All ({count})"
        else:
            label = f"\u25B6\u25B6 Run All in {self.selected_category} ({count})"
        self.run_all_button.config(text=label, state=("normal" if count else "disabled"))

    def _run_visible(self):
        entries = self._visible_commands()
        if not entries:
            messagebox.showinfo("Nothing to run", "There are no entries in the current view.")
            return

        runnable = [e for e in entries if not extract_placeholders(e.get("command", ""))]
        skipped_ids = {e["id"] for e in entries} - {e["id"] for e in runnable}
        skipped = [e for e in entries if e["id"] in skipped_ids]

        scope = "all categories" if self.selected_category == ALL_CATEGORY else f"'{self.selected_category}'"
        query = self.search_var.get().strip()
        if query and query.lower() != "search commands...":
            scope += f" matching \"{query}\""

        msg = f"This will launch {len(runnable)} entries in {scope}."
        if skipped:
            names = ", ".join(e["name"] for e in skipped)
            msg += f"\n\n{len(skipped)} skipped (need values filled in \u2014 run individually): {names}"
        msg += "\n\nContinue?"

        if not runnable:
            messagebox.showinfo("Nothing to run", "Every entry in this view needs values filled in \u2014 run them individually.")
            return

        if not messagebox.askyesno("Run all?", msg):
            return

        for entry in runnable:
            run_entry(entry, log=self._log)

    def _get_selected_entry(self):
        sel = self.tree.selection()
        if not sel:
            return None
        entry_id = sel[0]
        for cmd in self.data["commands"]:
            if cmd["id"] == entry_id:
                return cmd
        return None

    # -- CRUD actions ------------------------------------------------------
    def _known_categories(self):
        used = sorted({c["category"] for c in self.data["commands"]} | set(self.data["categories"]))
        return used or [UNCATEGORIZED]

    def _apply_autostart(self, entry):
        if entry.get("autostart") and extract_placeholders(entry.get("command", "")):
            messagebox.showwarning(
                "Heads up",
                f'"{entry["name"]}" uses {{{{placeholders}}}} that need values filled in each run.\n\n'
                "At boot there's no one to prompt, so it will run with the literal "
                "{{name}} text still in it and likely fail. Consider removing the "
                "placeholders for autostart entries, or leaving autostart off for this one."
            )
        try:
            set_entry_autostart(entry, entry.get("autostart", False))
        except NotImplementedError as e:
            messagebox.showwarning("Not supported", str(e))

    def _apply_schedule(self, entry):
        if entry.get("schedule_enabled") and extract_placeholders(entry.get("command", "")):
            messagebox.showwarning(
                "Heads up",
                f'"{entry["name"]}" uses {{{{placeholders}}}} that need values filled in each run.\n\n'
                "A scheduled run has no one to prompt either, so it will run with the literal "
                "{{name}} text still in it and likely fail. Consider removing the "
                "placeholders for scheduled entries, or leaving the schedule off for this one."
            )
        try:
            set_entry_schedule(entry, entry.get("schedule_enabled", False))
        except (NotImplementedError, RuntimeError) as e:
            messagebox.showwarning("Scheduling failed", str(e))

    def _add_entry(self):
        dialog = EntryDialog(self, self._known_categories())
        self.wait_window(dialog)
        if dialog.result:
            self.data["commands"].append(dialog.result)
            if dialog.result["category"] not in self.data["categories"]:
                self.data["categories"].append(dialog.result["category"])
            save_data(self.data)
            self._apply_autostart(dialog.result)
            self._apply_schedule(dialog.result)
            self._rebuild_hotkey_listener()
            self._refresh_categories()
            self._refresh_list()

    def _edit_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to edit first.")
            return
        dialog = EntryDialog(self, self._known_categories(), entry=entry)
        self.wait_window(dialog)
        if dialog.result:
            idx = next(i for i, c in enumerate(self.data["commands"]) if c["id"] == entry["id"])
            self.data["commands"][idx] = dialog.result
            if dialog.result["category"] not in self.data["categories"]:
                self.data["categories"].append(dialog.result["category"])
            save_data(self.data)
            self._apply_autostart(dialog.result)
            self._apply_schedule(dialog.result)
            self._rebuild_hotkey_listener()
            self._refresh_categories()
            self._refresh_list()

    def _delete_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to delete first.")
            return
        if messagebox.askyesno("Delete entry", f"Delete '{entry['name']}'?"):
            self.data["commands"] = [c for c in self.data["commands"] if c["id"] != entry["id"]]
            save_data(self.data)
            try:
                set_entry_autostart(entry, False)
            except NotImplementedError:
                pass
            try:
                set_entry_schedule(entry, False)
            except (NotImplementedError, RuntimeError):
                pass
            profile_dir = browser_profile_path(entry)
            if profile_dir and not (entry.get("browser_profile_dir") or "").strip() and os.path.isdir(profile_dir):
                if messagebox.askyesno("Browser profile",
                                       "Also delete this entry's saved browser profile (logins/cookies)?"):
                    shutil.rmtree(profile_dir, ignore_errors=True)
            self._rebuild_hotkey_listener()
            self._refresh_categories()
            self._refresh_list()

    def _run_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to run first.")
            return
        run_entry(entry, log=self._log)

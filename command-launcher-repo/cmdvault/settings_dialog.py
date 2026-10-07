"""settings_dialog -- split out of the former monolithic main.py."""
from datetime import datetime
from tkinter import filedialog
import json
from tkinter import messagebox
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import ttk
from .compat import HAVE_PYNPUT, HAVE_PYSTRAY
from .autostart import app_autostart_enabled, set_app_autostart, set_entry_autostart
from .config import APP_VERSION
from .data import _load_config, _normalize_vault_data, _save_config, get_data_dir, get_data_file, load_data, save_data, set_data_dir
from .hotkeys import AllKeybindsDialog, HotkeyRecorderDialog
from .platform_utils import is_linux
from .terminals import NAMED_LINUX_TERMINALS, run_entry
from .theme import COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_PANEL, COLOR_RED, COLOR_SIDEBAR, COLOR_SUBTEXT, COLOR_TEXT, FONT_HEADING, FONT_NORMAL, FONT_SMALL
from .updates import _version_is_newer, fetch_latest_release


# Settings dialog
# ---------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Settings")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        tk.Label(self, text="Settings", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(16, 8))

        self.autostart_var = tk.BooleanVar(value=app_autostart_enabled())
        tk.Checkbutton(self, text="Launch Command Vault when the computer starts",
                        variable=self.autostart_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_NORMAL,
                        command=self._toggle_app_autostart).pack(anchor="w", padx=16)

        note = ("Once this is on, you can also flip \u201cRun this automatically when the computer starts\u201d "
                "on individual entries in the Edit dialog.")
        tk.Label(self, text=note, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=340,
                 justify="left").pack(anchor="w", padx=16, pady=(6, 16))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Data Storage", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)
        tk.Label(self, text="Your commands.json is currently stored in:", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(6, 2))

        self.path_var = tk.StringVar(value=get_data_dir())
        path_entry = tk.Entry(self, textvariable=self.path_var, width=44, font=("Segoe UI", 9),
                               bg=COLOR_PANEL, fg=COLOR_SUBTEXT, relief="flat", state="readonly",
                               readonlybackground=COLOR_PANEL)
        path_entry.pack(fill="x", padx=16)

        tk.Button(self, text="Change Folder...", command=self._change_folder, bg=COLOR_ACCENT_DIM,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(anchor="w", padx=16, pady=(8, 4))

        tk.Label(self, text="Existing data moves automatically to the new folder.", bg=COLOR_BG,
                 fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(0, 12))

        backup_row = tk.Frame(self, bg=COLOR_BG)
        backup_row.pack(anchor="w", padx=16, pady=(0, 4))
        tk.Button(backup_row, text="Export Vault...", command=self._export_vault, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(side="left")
        tk.Button(backup_row, text="Import Vault...", command=self._import_vault, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(side="left", padx=(8, 0))

        tk.Label(self, text="Export saves all your categories and commands to a single file \u2014 cheap "
                             "insurance before big edits or moving to a new machine. Import replaces your "
                             "current vault with one from a file.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=360, justify="left"
                 ).pack(anchor="w", padx=16, pady=(0, 16))

        if is_linux():
            tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

            tk.Label(self, text="Terminal", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                     ).pack(anchor="w", padx=16)
            tk.Label(self, text="Which terminal \"Open in Terminal\" mode uses. Auto-detect tries common "
                                 "terminals in order; pick one directly if you know what you have installed.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=360, justify="left"
                     ).pack(anchor="w", padx=16, pady=(6, 8))

            cfg = _load_config()
            saved_pref = cfg.get("preferred_terminal", "auto")
            terminal_options = ["Auto-detect"] + list(NAMED_LINUX_TERMINALS.keys()) + ["Custom command..."]
            if saved_pref == "auto":
                initial = "Auto-detect"
            elif saved_pref == "custom":
                initial = "Custom command..."
            elif saved_pref in NAMED_LINUX_TERMINALS:
                initial = saved_pref
            else:
                initial = "Auto-detect"

            self.terminal_var = tk.StringVar(value=initial)
            terminal_combo = ttk.Combobox(self, textvariable=self.terminal_var, values=terminal_options,
                                           state="readonly", width=30, font=FONT_NORMAL)
            terminal_combo.pack(anchor="w", padx=16)
            terminal_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_custom_template_visibility())

            self.custom_template_var = tk.StringVar(value=cfg.get("custom_terminal_template", ""))
            self.custom_template_label = tk.Label(self, text="Custom command (use %CMD% where the command goes):",
                                                    bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w")
            self.custom_template_entry = tk.Entry(self, textvariable=self.custom_template_var, width=44,
                                                    font=("Segoe UI", 9), bg=COLOR_PANEL, fg=COLOR_TEXT,
                                                    insertbackground=COLOR_TEXT, relief="flat")
            example = tk.Label(self, text='Example: kitty bash -c "%CMD%; exec bash"',
                                bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8))
            self.custom_template_example = example

            self._sync_custom_template_visibility()

            btn_row = tk.Frame(self, bg=COLOR_BG)
            btn_row.pack(anchor="w", padx=16, pady=(10, 16))
            tk.Button(btn_row, text="Save", command=self._save_terminal_pref, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4).pack(side="left")
            tk.Button(btn_row, text="Test", command=self._test_terminal, bg=COLOR_PANEL, fg=COLOR_TEXT,
                      relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Global Hotkey", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)

        if not HAVE_PYNPUT:
            tk.Label(self, text="Install pynput to enable this:\npip install pynput",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, justify="left"
                     ).pack(anchor="w", padx=16, pady=(6, 16))
        else:
            tray_note = ("with a tray icon to reopen or quit" if HAVE_PYSTRAY else
                         "by minimizing (install pystray too for a proper tray icon instead)")
            tk.Label(self, text=f"Press this combo anytime \u2014 even with Command Vault closed \u2014 to bring "
                                 f"the window back. Closing the window then keeps running in the background "
                                 f"{tray_note}.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=360, justify="left"
                     ).pack(anchor="w", padx=16, pady=(6, 10))

            cfg = _load_config()
            display = cfg.get("hotkey_display", "Not set")
            self.hotkey_display_var = tk.StringVar(value=display)
            tk.Label(self, textvariable=self.hotkey_display_var, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                     font=("Segoe UI", 11, "bold"), padx=10, pady=6).pack(anchor="w", padx=16, fill="x")

            hk_btn_row = tk.Frame(self, bg=COLOR_BG)
            hk_btn_row.pack(anchor="w", padx=16, pady=(8, 4))
            tk.Button(hk_btn_row, text="Record Shortcut...", command=self._record_hotkey, bg=COLOR_ACCENT,
                      fg=COLOR_SIDEBAR, relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4
                      ).pack(side="left")
            tk.Button(hk_btn_row, text="Clear", command=self._clear_hotkey, bg=COLOR_PANEL, fg=COLOR_RED,
                      relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))
            tk.Button(hk_btn_row, text="See All Keybinds", command=self._open_all_keybinds, bg=COLOR_PANEL,
                      fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))

            if is_linux():
                tk.Label(self, text="Linux note: needs an X11 session. On native Wayland this generally won't "
                                     "trigger even while Command Vault is open and focused, since Wayland blocks "
                                     "cross-app input capture by design.",
                         bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=360, justify="left"
                         ).pack(anchor="w", padx=16, pady=(4, 16))
            else:
                tk.Label(self, text="", bg=COLOR_BG).pack(pady=(0, 4))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Insert Input Box Shortcut", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)
        tk.Label(self, text="Used inside the command box in Add/Edit Entry to insert a {{name}} placeholder "
                             "at the cursor \u2014 no extra install needed, this works purely within the app.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=360, justify="left"
                 ).pack(anchor="w", padx=16, pady=(6, 10))

        ph_cfg = _load_config()
        ph_display = ph_cfg.get("insert_placeholder_display", "Ctrl+I (default)")
        self.placeholder_shortcut_display_var = tk.StringVar(value=ph_display)
        tk.Label(self, textvariable=self.placeholder_shortcut_display_var, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=("Segoe UI", 11, "bold"), padx=10, pady=6).pack(anchor="w", padx=16, fill="x")

        ph_btn_row = tk.Frame(self, bg=COLOR_BG)
        ph_btn_row.pack(anchor="w", padx=16, pady=(8, 16))
        tk.Button(ph_btn_row, text="Record Shortcut...", command=self._record_placeholder_shortcut,
                  bg=COLOR_ACCENT, fg=COLOR_SIDEBAR, relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4
                  ).pack(side="left")
        tk.Button(ph_btn_row, text="Reset to Ctrl+I", command=self._clear_placeholder_shortcut, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Updates", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)
        tk.Label(self, text=f"You're running v{APP_VERSION}.", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(6, 8))

        auto_check_cfg = _load_config()
        self.auto_update_var = tk.BooleanVar(value=auto_check_cfg.get("auto_update_check", True))
        tk.Checkbutton(self, text="Check for updates automatically (about once a day)",
                        variable=self.auto_update_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_NORMAL,
                        command=self._toggle_auto_update_check).pack(anchor="w", padx=16)

        self.update_status_var = tk.StringVar(value="")
        tk.Button(self, text="Check for Updates", command=self._check_for_updates_manual, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Label(self, textvariable=self.update_status_var, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=360, justify="left").pack(anchor="w", padx=16, pady=(0, 16))

        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(pady=(0, 16))

    def _toggle_auto_update_check(self):
        cfg = _load_config()
        cfg["auto_update_check"] = self.auto_update_var.get()
        _save_config(cfg)

    def _check_for_updates_manual(self):
        self.update_status_var.set("Checking...")

        def _run():
            result = fetch_latest_release()
            cfg = _load_config()
            cfg["last_update_check"] = time.time()
            _save_config(cfg)

            def _apply():
                if not self.winfo_exists():
                    return  # Settings dialog was closed before the check finished
                if result is None:
                    self.update_status_var.set(
                        "Couldn't check for updates (no network, or GitHub is unreachable right now).")
                    return
                tag, html_url = result
                if _version_is_newer(tag, APP_VERSION):
                    self.update_status_var.set(f"{tag} is available.")
                    if messagebox.askyesno("Update available",
                                            f"Command Vault {tag} is available (you have v{APP_VERSION}).\n\n"
                                            f"Open the release page?"):
                        self.master_app._open_url(html_url)
                else:
                    self.update_status_var.set(f"You're on the latest version (v{APP_VERSION}).")

            self.master_app._post_to_main_thread(_apply)

        threading.Thread(target=_run, daemon=True).start()

    def _record_placeholder_shortcut(self):
        dialog = HotkeyRecorderDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        display_string, _pynput_string, tk_bind_string = dialog.result
        cfg = _load_config()
        cfg["insert_placeholder_display"] = display_string
        cfg["insert_placeholder_tkbind"] = tk_bind_string
        _save_config(cfg)
        self.placeholder_shortcut_display_var.set(display_string)

    def _clear_placeholder_shortcut(self):
        cfg = _load_config()
        cfg.pop("insert_placeholder_display", None)
        cfg.pop("insert_placeholder_tkbind", None)
        _save_config(cfg)
        self.placeholder_shortcut_display_var.set("Ctrl+I (default)")

    def _record_hotkey(self):
        dialog = HotkeyRecorderDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        display_string, pynput_string, _tk_bind_string = dialog.result

        current = _load_config().get("hotkey_pynput")
        conflicts = self.master_app._all_used_hotkeys(exclude_pynput=current)
        if pynput_string in conflicts:
            messagebox.showwarning("Already in use", f"{display_string} is already assigned to "
                                                        f"{conflicts[pynput_string]}. Pick a different combo.")
            return

        cfg = _load_config()
        cfg["hotkey_display"] = display_string
        cfg["hotkey_pynput"] = pynput_string
        _save_config(cfg)
        self.hotkey_display_var.set(display_string)
        self.master_app._rebuild_hotkey_listener()
        self.master_app._log(f"Global hotkey set: {display_string}")

    def _clear_hotkey(self):
        cfg = _load_config()
        cfg.pop("hotkey_display", None)
        cfg.pop("hotkey_pynput", None)
        _save_config(cfg)
        self.hotkey_display_var.set("Not set")
        self.master_app._rebuild_hotkey_listener()
        self.master_app._log("Global hotkey cleared.")

    def _open_all_keybinds(self):
        AllKeybindsDialog(self, self.master_app)

    def _sync_custom_template_visibility(self):
        if self.terminal_var.get() == "Custom command...":
            self.custom_template_label.pack(anchor="w", padx=16, pady=(6, 2))
            self.custom_template_entry.pack(fill="x", padx=16)
            self.custom_template_example.pack(anchor="w", padx=16, pady=(2, 0))
        else:
            self.custom_template_label.pack_forget()
            self.custom_template_entry.pack_forget()
            self.custom_template_example.pack_forget()

    def _current_terminal_pref(self):
        choice = self.terminal_var.get()
        if choice == "Auto-detect":
            return "auto", ""
        if choice == "Custom command...":
            return "custom", self.custom_template_var.get().strip()
        return choice, ""

    def _save_terminal_pref(self):
        pref, template = self._current_terminal_pref()
        if pref == "custom" and "%CMD%" not in template:
            messagebox.showwarning("Missing %CMD%", "Your custom command needs a %CMD% placeholder for where "
                                                       "the actual command gets inserted.")
            return
        cfg = _load_config()
        cfg["preferred_terminal"] = pref
        cfg["custom_terminal_template"] = template
        _save_config(cfg)
        messagebox.showinfo("Saved", "Terminal preference saved.")

    def _test_terminal(self):
        pref, template = self._current_terminal_pref()
        cfg = _load_config()
        cfg["preferred_terminal"] = pref
        cfg["custom_terminal_template"] = template
        _save_config(cfg)
        test_entry = {"id": "test", "name": "Terminal Test", "command": 'echo "Command Vault terminal test - it works!"',
                      "working_dir": "", "run_mode": "terminal", "entry_type": "command"}
        run_entry(test_entry, log=self.master_app._log)

    def _toggle_app_autostart(self):
        try:
            set_app_autostart(self.autostart_var.get())
        except NotImplementedError as e:
            messagebox.showwarning("Not supported", str(e))
            self.autostart_var.set(app_autostart_enabled())

    def _change_folder(self):
        new_dir = filedialog.askdirectory(title="Choose folder to store Command Vault's data",
                                           initialdir=get_data_dir())
        if not new_dir:
            return
        try:
            set_data_dir(new_dir)
        except OSError as e:
            messagebox.showerror("Couldn't change folder", str(e))
            return
        self.path_var.set(get_data_dir())
        self.master_app.data = load_data()
        self.master_app._refresh_categories()
        self.master_app._refresh_list()
        messagebox.showinfo("Data folder updated", f"Command Vault now stores its data in:\n{new_dir}")

    def _export_vault(self):
        default_name = f"command-vault-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path = filedialog.asksaveasfilename(
            title="Export Command Vault", defaultextension=".json", initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            # Serialize the in-memory vault rather than copying commands.json
            # off disk -- on a brand-new install with an empty vault, no
            # file has been written yet, and this way Export can never miss
            # a change even if the on-disk copy were somehow stale.
            with open(path, "w") as f:
                json.dump(self.master_app.data, f, indent=4)
        except OSError as e:
            messagebox.showerror("Export failed", str(e))
            return
        n = len(self.master_app.data.get("commands", []))
        messagebox.showinfo("Vault exported", f"Exported {n} command{'s' if n != 1 else ''} to:\n{path}")

    def _import_vault(self):
        path = filedialog.askopenfilename(title="Import Command Vault",
                                           filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Import failed", f"Couldn't read that file as a Command Vault export:\n{e}")
            return

        try:
            imported = _normalize_vault_data(raw)
        except (AttributeError, TypeError):
            # e.g. valid JSON but not an object/list shaped like a vault
            messagebox.showerror("Import failed", "That file doesn't look like a Command Vault export.")
            return

        current_n = len(self.master_app.data.get("commands", []))
        new_n = len(imported.get("commands", []))
        proceed = messagebox.askyesno(
            "Replace current vault?",
            f"This will replace your current vault ({current_n} command{'s' if current_n != 1 else ''}) "
            f"with the {new_n} command{'s' if new_n != 1 else ''} from:\n{path}\n\n"
            "Your current vault will be backed up first. Continue?")
        if not proceed:
            return

        # Cheap insurance against importing the wrong file: back up what's
        # about to be overwritten, same convention as the corrupted-file
        # quarantine in load_data().
        data_file = get_data_file()
        if os.path.exists(data_file):
            backup_path = f"{data_file}.pre-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            try:
                shutil.copy2(data_file, backup_path)
            except OSError:
                backup_path = None
        else:
            backup_path = None

        try:
            save_data(imported)
        except OSError as e:
            messagebox.showerror("Import failed", f"Couldn't write the new vault:\n{e}")
            return

        self.master_app.data = imported
        self.master_app._refresh_categories()
        self.master_app._refresh_list()
        # hotkey_pynput on each entry is the live source of truth for global
        # hotkeys, so this actually re-registers any imported entries' hotkeys.
        self.master_app._rebuild_hotkey_listener()
        # autostart's source of truth is an OS-level file per entry, not the
        # JSON field, so imported entries with autostart=True need that file
        # (re)created here or they'd show "on" in the UI without actually
        # running at login on this machine.
        autostart_failures = 0
        for entry in imported.get("commands", []):
            if entry.get("autostart"):
                try:
                    set_entry_autostart(entry, True)
                except (NotImplementedError, OSError):
                    autostart_failures += 1

        msg = f"Imported {new_n} command{'s' if new_n != 1 else ''}."
        if backup_path:
            msg += f"\n\nYour previous vault was backed up to:\n{backup_path}"
        if autostart_failures:
            msg += (f"\n\n{autostart_failures} autostart entr{'y' if autostart_failures == 1 else 'ies'} "
                     "couldn't be registered on this machine/OS and may need re-enabling manually.")
        messagebox.showinfo("Vault imported", msg)


# ---------------------------------------------------------------------------

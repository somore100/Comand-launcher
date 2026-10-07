"""hotkeys -- split out of the former monolithic main.py."""
import base64
import io
import tkinter as tk
from tkinter import ttk
from .compat import PILImage
from .data import _load_config
from .theme import COLOR_BG, COLOR_PANEL, COLOR_ROW_ALT, COLOR_SUBTEXT, COLOR_TEXT, FONT_HEADING, FONT_SMALL


# Global hotkey: capture (local, dialog-scoped) and tray icon (for background mode)
# ---------------------------------------------------------------------------
MODIFIER_KEYSYMS = {
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt",
    "Shift_L": "shift", "Shift_R": "shift",
    "Super_L": "cmd", "Super_R": "cmd",
}

MODIFIER_ORDER = ["ctrl", "alt", "shift", "cmd"]

TK_MODIFIER_NAMES = {"ctrl": "Control", "alt": "Alt", "shift": "Shift", "cmd": "Super"}

SPECIAL_KEYSYM_TO_PYNPUT = {
    "space": "<space>", "Return": "<enter>", "Escape": "<esc>", "Tab": "<tab>",
    "BackSpace": "<backspace>", "Delete": "<delete>",
    "Up": "<up>", "Down": "<down>", "Left": "<left>", "Right": "<right>",
    "Home": "<home>", "End": "<end>", "Page_Up": "<page_up>", "Page_Down": "<page_down>",
    "F1": "<f1>", "F2": "<f2>", "F3": "<f3>", "F4": "<f4>", "F5": "<f5>", "F6": "<f6>",
    "F7": "<f7>", "F8": "<f8>", "F9": "<f9>", "F10": "<f10>", "F11": "<f11>", "F12": "<f12>",
}


def tk_keysym_to_pynput(keysym):
    if keysym in SPECIAL_KEYSYM_TO_PYNPUT:
        return SPECIAL_KEYSYM_TO_PYNPUT[keysym]
    if len(keysym) == 1:
        return keysym.lower()
    return None


TRAY_ICON_PNG_B64 = (
    "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"
    "gg=="
)


def build_tray_image(size=64):
    """Decodes the app's packaging/icon.png logo (baked in as base64 below)
    and resizes it to the requested size. Baked in rather than loaded from
    disk because PyInstaller builds never bundle packaging/ as a data file
    -- this keeps the tray icon self-contained the same way the earlier
    procedurally-drawn padlock placeholder was."""
    img = PILImage.open(io.BytesIO(base64.b64decode(TRAY_ICON_PNG_B64))).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), PILImage.LANCZOS)
    return img


class HotkeyRecorderDialog(tk.Toplevel):
    """Minecraft-style capture: click Record, hold modifiers + press a key,
    it finalizes immediately. Local Tkinter key events are enough here since
    this dialog has focus while recording -- only *triggering* the saved
    hotkey later needs to be global (that's pynput's job, in CommandVault)."""
    def __init__(self, master):
        super().__init__(master)
        self.result = None
        self.title("Record Shortcut")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()
        self.held_modifiers = set()

        self.status_var = tk.StringVar(value="Press a key combination\u2026")
        tk.Label(self, textvariable=self.status_var, bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 14, "bold")
                 ).pack(padx=36, pady=(28, 8))
        tk.Label(self, text="Hold Ctrl/Alt/Shift/Super and press a key. Esc to cancel.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(padx=20, pady=(0, 24))

        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.focus_set()

    def _on_key_press(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self.held_modifiers.add(MODIFIER_KEYSYMS[keysym])
            self._update_status()
            return
        if keysym == "Escape":
            self.result = None
            self.destroy()
            return

        pynput_key = tk_keysym_to_pynput(keysym)
        if not pynput_key:
            self.status_var.set(f"'{keysym}' isn't supported \u2014 try another key")
            return
        if not self.held_modifiers:
            self.status_var.set("Add at least one modifier (Ctrl/Alt/Shift/Super)")
            return

        mods = [m for m in MODIFIER_ORDER if m in self.held_modifiers]
        pynput_string = "+".join([f"<{m}>" for m in mods] + [pynput_key])
        display_key = keysym if len(keysym) > 1 else keysym.upper()
        display_string = "+".join([m.capitalize() for m in mods] + [display_key])
        tk_bind_string = "<" + "-".join([TK_MODIFIER_NAMES[m] for m in mods] + [keysym]) + ">"
        self.result = (display_string, pynput_string, tk_bind_string)
        self.destroy()

    def _on_key_release(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self.held_modifiers.discard(MODIFIER_KEYSYMS[keysym])
            self._update_status()

    def _update_status(self):
        if self.held_modifiers:
            mods = "+".join(m.capitalize() for m in MODIFIER_ORDER if m in self.held_modifiers)
            self.status_var.set(f"{mods}+\u2026 (now press a key)")
        else:
            self.status_var.set("Press a key combination\u2026")


class AllKeybindsDialog(tk.Toplevel):
    """Read-only overview of every configured shortcut: the app-level
    reopen hotkey, the local insert-input-box shortcut, and every entry's
    own launch hotkey. Actual changes happen where each is defined."""
    def __init__(self, master, app):
        super().__init__(master)
        self.title("All Keybinds")
        self.configure(bg=COLOR_BG)
        self.geometry("460x420")
        self.transient(master)
        self.grab_set()

        tk.Label(self, text="All Keybinds", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(16, 8))

        list_frame = tk.Frame(self, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=16)

        columns = ("what", "shortcut")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="none")
        tree.heading("what", text="Command / Action")
        tree.heading("shortcut", text="Shortcut")
        tree.column("what", width=280, anchor="w")
        tree.column("shortcut", width=140, anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        cfg = _load_config()
        rows = []
        app_hk = cfg.get("hotkey_display")
        rows.append(("App: Show Command Vault", app_hk or "Not set"))
        ph_hk = cfg.get("insert_placeholder_display", "Ctrl+I (default)")
        rows.append(("Insert Input Box (in command editor)", ph_hk))
        for entry in app.data.get("commands", []):
            hk = entry.get("hotkey_display")
            if hk:
                rows.append((f'{entry.get("icon", "")} {entry["name"]} ({entry["category"]})', hk))

        for i, (what, shortcut) in enumerate(rows):
            tag = "even" if i % 2 else "odd"
            tree.insert("", tk.END, values=(what, shortcut), tags=(tag,))
        tree.tag_configure("odd", background=COLOR_PANEL)
        tree.tag_configure("even", background=COLOR_ROW_ALT)

        entry_count = len(rows) - 2
        if entry_count == 0:
            tk.Label(self, text="No per-command shortcuts set yet \u2014 add one from an entry's Edit dialog.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=420, justify="left"
                     ).pack(anchor="w", padx=16, pady=(8, 0))

        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(pady=16)


# ---------------------------------------------------------------------------

"""bulk_dialog -- "Add many": paste one command per line, preview, add them all."""
import tkinter as tk
from tkinter import messagebox, ttk
from .bulk import build_entries, parse_bulk_lines
from .theme import (COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_PANEL, COLOR_SIDEBAR, COLOR_SUBTEXT,
                    COLOR_TEXT, FONT_NORMAL, FONT_SMALL, UNCATEGORIZED)

HELP = ("One command or script path per line. Names are made from the file name, or from the folder "
        "name when several lines would clash. Use  Name :: command  (or a tab) to choose a name yourself. "
        "Blank lines and lines starting with # are ignored.")


class BulkAddDialog(tk.Toplevel):
    def __init__(self, master, categories):
        super().__init__(master)
        self.result = None  # list of entry dicts when confirmed
        self.title("Add Multiple Entries")
        self.configure(bg=COLOR_BG)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(680, sw - 20)}x{min(620, int(sh * 0.9))}")
        self.minsize(min(480, sw - 20), min(360, int(sh * 0.9)))
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(master)
        self.grab_set()

        bar = tk.Frame(self, bg=COLOR_BG)
        bar.pack(side="bottom", fill="x", padx=16, pady=12)
        self.add_btn = tk.Button(bar, text="Add 0", command=self._confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                                 font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4)
        self.add_btn.pack(side="right")
        tk.Button(bar, text="Cancel", command=self.destroy, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(side="right", padx=(0, 8))
        tk.Label(self, text=HELP, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=640,
                 justify="left", anchor="w").pack(fill="x", padx=16, pady=(14, 6))

        self.text = tk.Text(self, height=10, bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
                            relief="flat", font=("DejaVu Sans Mono", 9), wrap="none", undo=True, padx=6, pady=4)
        self.text.pack(fill="x", padx=16)
        self.text.bind("<<Modified>>", self._on_modified)

        opts = tk.Frame(self, bg=COLOR_BG)
        opts.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(opts, text="Category", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).grid(row=0, column=0, sticky="w")
        self.category_var = tk.StringVar(value=categories[0] if categories else UNCATEGORIZED)
        ttk.Combobox(opts, textvariable=self.category_var, values=categories or [UNCATEGORIZED], width=26,
                     font=FONT_NORMAL).grid(row=1, column=0, sticky="w", padx=(0, 16))

        self.mode_var = tk.StringVar(value="terminal")
        mode = tk.Frame(opts, bg=COLOR_BG)
        mode.grid(row=1, column=1, sticky="w")
        for text, val in (("Open in Terminal", "terminal"), ("Run Silently", "silent")):
            tk.Radiobutton(mode, text=text, variable=self.mode_var, value=val, bg=COLOR_BG, fg=COLOR_TEXT,
                           selectcolor=COLOR_PANEL, activebackground=COLOR_BG, activeforeground=COLOR_TEXT,
                           font=FONT_SMALL).pack(side="left", padx=(0, 10))
        tk.Label(opts, text="Run Mode", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).grid(row=0, column=1, sticky="w")

        self.folder_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Run each one in its own folder (set the working directory to the script's folder)",
                       variable=self.folder_var, command=self._refresh_preview, bg=COLOR_BG, fg=COLOR_TEXT,
                       selectcolor=COLOR_PANEL, activebackground=COLOR_BG, activeforeground=COLOR_TEXT,
                       font=FONT_SMALL).pack(anchor="w", padx=16, pady=(8, 0))

        tk.Label(self, text="Preview", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(anchor="w", padx=16, pady=(10, 2))
        pf = tk.Frame(self, bg=COLOR_BG)
        pf.pack(fill="both", expand=True, padx=16)
        self.preview = ttk.Treeview(pf, columns=("name", "command", "folder"), show="headings", height=8)
        for col, label, w in (("name", "Name", 150), ("command", "Command", 300), ("folder", "Runs in", 170)):
            self.preview.heading(col, text=label)
            self.preview.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(pf, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.preview.pack(side="left", fill="both", expand=True)

        self.text.focus_set()
        self._refresh_preview()

    def _on_modified(self, _event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._refresh_preview()

    def _entries(self):
        rows = parse_bulk_lines(self.text.get("1.0", "end-1c"))
        return build_entries(rows, self.category_var.get().strip() or UNCATEGORIZED,
                             self.mode_var.get(), self.folder_var.get())

    def _refresh_preview(self):
        self.preview.delete(*self.preview.get_children())
        entries = self._entries()
        for e in entries:
            self.preview.insert("", tk.END, values=(e["name"], e["command"], e["working_dir"] or "\u2014"))
        self.add_btn.configure(text=f"Add {len(entries)}", state="normal" if entries else "disabled")

    def _confirm(self):
        entries = self._entries()
        if not entries:
            messagebox.showinfo("Nothing to add", "Paste at least one command first.", parent=self)
            return
        self.result = entries
        self.destroy()

"""runlog_dialog -- shows the outcome and captured output of an entry's last scheduled run."""
import tkinter as tk
from tkinter import ttk
from .runstatus import read_run_log_tail, read_run_status
from .theme import COLOR_BG, COLOR_GREEN, COLOR_PANEL, COLOR_RED, COLOR_SUBTEXT, COLOR_TEXT, FONT_NORMAL, FONT_SMALL


class RunLogDialog(tk.Toplevel):
    def __init__(self, master, entry):
        super().__init__(master, bg=COLOR_BG)
        self.title(f"Last scheduled run \u2014 {entry['name']}")
        self.geometry("640x420")
        self.transient(master)

        status = read_run_status(entry["id"])
        if status is None:
            headline, color = "No scheduled run has been recorded yet.", COLOR_SUBTEXT
        elif status["failed"]:
            headline, color = f"\u26A0 Failed with exit code {status['exit_code']}  \u00b7  {status['when']}", COLOR_RED
        else:
            headline, color = f"\u2713 Succeeded (exit code 0)  \u00b7  {status['when']}", COLOR_GREEN
        tk.Label(self, text=headline, bg=COLOR_BG, fg=color, font=FONT_NORMAL, anchor="w"
                 ).pack(fill="x", padx=16, pady=(14, 6))

        body = tk.Frame(self, bg=COLOR_PANEL)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        text = tk.Text(body, bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat", wrap="word", padx=8, pady=6,
                       font=("DejaVu Sans Mono", 9))
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        output = read_run_log_tail(entry["id"])
        text.insert("1.0", output if output else "(no output captured)")
        text.configure(state="disabled")
        text.see("end")

        tk.Label(self, text="Output of the most recent scheduled run (last 64 KB). Scheduled runs overwrite "
                            "this each time they fire.", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 anchor="w").pack(fill="x", padx=16)
        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(anchor="e", padx=16, pady=(6, 14))

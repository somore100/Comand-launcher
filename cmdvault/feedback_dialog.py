"""feedback_dialog -- the "Leave Feedback" window. Pairs with feedback.py; to reuse
in another app, copy both plus scrollframe.py and adapt the theme import."""
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from . import feedback as fb
from .scrollframe import ScrollableBody, fit_dialog
from .theme import (COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_PANEL, COLOR_SIDEBAR, COLOR_SUBTEXT,
                    COLOR_TEXT, FONT_HEADING, FONT_NORMAL, FONT_SMALL)


class FeedbackDialog(tk.Toplevel):
    def __init__(self, master, cfg):
        super().__init__(master)
        self.cfg = cfg
        self._sysinfo = None
        self._sending = False
        self.title("Leave Feedback")
        self.configure(bg=COLOR_BG)
        self.resizable(False, True)
        self.transient(master)
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())

        scroll = ScrollableBody(self)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        def label(text):
            tk.Label(body, text=text, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w"
                     ).pack(anchor="w", padx=16, pady=(10, 2))

        def entry_style():
            return dict(font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
                        relief="flat")

        tk.Label(body, text="Leave Feedback", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(body, text=f"{cfg.app_name}  ·  version {cfg.app_version}", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(2, 0))

        label("Report type")
        self.type_var = tk.StringVar(value="Bug Report")
        ttk.Combobox(body, textvariable=self.type_var, values=list(fb.REPORT_TYPES), state="readonly",
                     width=30).pack(anchor="w", padx=16)

        label("Your name (optional)")
        self.name_var = tk.StringVar()
        tk.Entry(body, textvariable=self.name_var, width=44, **entry_style()).pack(anchor="w", padx=16, ipady=3)

        label("Title *")
        self.title_var = tk.StringVar()
        tk.Entry(body, textvariable=self.title_var, width=44, **entry_style()).pack(anchor="w", padx=16, ipady=3)
        tk.Label(body, text="e.g. \"UI is not working\" or \"Feature suggestion: custom themes\"", bg=COLOR_BG,
                 fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w", padx=16)

        label("Description *")
        self.desc = tk.Text(body, width=52, height=9, wrap="word", **entry_style())
        self.desc.pack(anchor="w", padx=16)

        self.include_var = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="Include my computer specifications", variable=self.include_var,
                       command=self._toggle_sysinfo, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                       activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                       ).pack(anchor="w", padx=16, pady=(12, 0))
        self.sys_label = tk.Label(body, text="", bg=COLOR_PANEL, fg=COLOR_SUBTEXT, font=("Consolas", 8),
                                  justify="left", anchor="w", wraplength=420, padx=8, pady=6)
        tk.Label(body, text="Only the items shown when you tick this are sent: no username, computer name, "
                            "serial numbers or files.", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8),
                 wraplength=420, justify="left").pack(anchor="w", padx=16, pady=(2, 0))
        self.sys_label.pack(anchor="w", padx=16, pady=(4, 10), fill="x")
        self.sys_label.pack_forget()

        self.status_var = tk.StringVar(value="")
        tk.Label(scroll.footer, textvariable=self.status_var, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=420, justify="left").pack(anchor="w", padx=16, pady=(6, 0))
        bar = tk.Frame(scroll.footer, bg=COLOR_BG)
        bar.pack(fill="x", padx=16, pady=(6, 12))
        self.send_btn = tk.Button(bar, text="Send", command=self._send, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                                  font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4)
        self.send_btn.pack(side="right")
        tk.Button(bar, text="Cancel", command=self.destroy, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(side="right", padx=(0, 8))
        tk.Button(bar, text="Copy report", command=self._copy, bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat",
                  font=FONT_SMALL, padx=10, pady=4).pack(side="left")

        fit_dialog(self, master)

    def _toggle_sysinfo(self):
        if not self.include_var.get():
            self.sys_label.pack_forget()
            return
        if self._sysinfo is None:
            self.config(cursor="watch")
            self.update_idletasks()
            self._sysinfo = fb.collect_system_info(self.cfg.app_version)
            self.config(cursor="")
        self.sys_label.configure(text="\n".join(f"{k}: {v}" for k, v in self._sysinfo))
        self.sys_label.pack(anchor="w", padx=16, pady=(4, 10), fill="x")
        self.update_idletasks()
        self.minsize(self.winfo_width(), 240)

    def _collect(self):
        """(subject, body) or None after showing a validation message."""
        rtype = self.type_var.get()
        title = self.title_var.get()
        desc = self.desc.get("1.0", "end-1c")
        error = fb.validate(rtype, title, desc)
        if error:
            messagebox.showwarning("Missing info", error, parent=self)
            return None
        sysinfo = self._sysinfo if self.include_var.get() else None
        return (fb.build_subject(self.cfg, rtype, title),
                fb.build_body(self.cfg, rtype, title, desc, self.name_var.get(), sysinfo))

    def _copy(self):
        report = self._collect()
        if not report:
            return
        self.clipboard_clear()
        self.clipboard_append(f"Subject: {report[0]}\n\n{report[1]}")
        self.status_var.set("Report copied to the clipboard.")

    def _send(self):
        if self._sending:
            return
        report = self._collect()
        if not report:
            return
        subject, body = report
        if self.cfg.relay_url:
            self._sending = True
            self.send_btn.configure(state="disabled", text="Sending...")
            self.status_var.set("Sending...")
            threading.Thread(target=self._relay_worker, args=(subject, body), daemon=True).start()
        else:
            self._send_mailto(subject, body)

    def _relay_worker(self, subject, body):
        ok, msg = fb.send_via_relay(self.cfg, subject, body)
        try:
            self.after(0, self._relay_done, ok, msg, subject, body)
        except tk.TclError:
            pass  # dialog closed while sending

    def _relay_done(self, ok, msg, subject, body):
        self._sending = False
        self.send_btn.configure(state="normal", text="Send")
        if ok:
            messagebox.showinfo("Feedback sent", msg, parent=self)
            self.destroy()
            return
        self.status_var.set(msg)
        if messagebox.askyesno("Couldn't send", f"{msg}\n\nOpen your email app with the report instead?",
                               parent=self):
            self._send_mailto(subject, body)

    def _send_mailto(self, subject, body):
        url, truncated = fb.build_mailto(self.cfg, subject, body)
        self.clipboard_clear()
        self.clipboard_append(f"To: {self.cfg.support_email}\nSubject: {subject}\n\n{body}")
        if fb.open_mailto(url):
            messagebox.showinfo(
                "Almost done",
                "Your email app should open with the report filled in. Press Send there to finish."
                + ("\n\nThe report was long, so the full text is on your clipboard to paste." if truncated else ""),
                parent=self)
            self.destroy()
        else:
            messagebox.showerror(
                "No email app found",
                f"Couldn't open an email app. The full report was copied to your clipboard: paste it into an "
                f"email to {self.cfg.support_email}.", parent=self)

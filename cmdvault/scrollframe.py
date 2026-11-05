"""scrollframe -- scrollable dialog body with a pinned footer, plus screen-aware sizing."""
import tkinter as tk
from tkinter import ttk

from .theme import COLOR_BG


class ScrollableBody(tk.Frame):
    """A frame holding a scrollable content area (`.inner`) and a footer (`.footer`)
    that stays pinned to the bottom. The scrollbar hides when everything fits."""

    def __init__(self, master, bg=COLOR_BG):
        super().__init__(master, bg=bg)
        self._bg = bg
        self.footer = tk.Frame(self, bg=bg)
        self.footer.pack(side="bottom", fill="x")

        area = tk.Frame(self, bg=bg)
        area.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(area, bg=bg, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bound = False
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    def sync(self):
        """Make the canvas exactly as big as its content right now, so the
        dialog's requested size is the real one (Configure events haven't been
        processed yet when a dialog is first sized)."""
        self.update_idletasks()
        self.canvas.configure(width=self.inner.winfo_reqwidth(), height=self.inner.winfo_reqheight())
        self.update_idletasks()

    def _on_yscroll(self, first, last):
        self.scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        elif not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y")

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        # Canvas has no natural height; track the content so the dialog can size to it.
        self.canvas.configure(width=self.inner.winfo_reqwidth(), height=self.inner.winfo_reqheight())

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, _event=None):
        if self._bound:
            return
        self._bound = True
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", self._on_wheel)
        self.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, event=None):
        # Leave events fire when moving onto a child; only unbind when truly outside.
        if event is not None:
            x, y = self.winfo_pointerxy()
            if self.winfo_containing(x, y) is not None and \
                    str(self.winfo_containing(x, y)).startswith(str(self)):
                return
        self._bound = False
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(seq)

    def _on_wheel(self, event):
        if isinstance(event.widget, tk.Text):
            return
        if self.scrollbar.winfo_ismapped() is False:
            return
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * 2, "units")


def fit_dialog(dialog, parent=None, max_height_fraction=0.92):
    """Size `dialog` to its content, capped to the screen height, centred over `parent`."""
    dialog.update_idletasks()
    for child in dialog.winfo_children():
        if isinstance(child, ScrollableBody):
            child.sync()
    parent = parent or dialog.master
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    width = min(dialog.winfo_reqwidth(), screen_w - 20)
    height = min(dialog.winfo_reqheight(), int(screen_h * max_height_fraction))
    try:
        px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    except tk.TclError:
        px, py = (screen_w - width) // 2, (screen_h - height) // 2
    x = max(0, min(px, screen_w - width))
    y = max(0, min(py, screen_h - height - 40))
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    # Resizable by the user, but never smaller than the content needs (width) or 320 px tall.
    dialog.minsize(width, min(height, 320))


class CollapsibleSection(tk.Frame):
    """A header row (arrow, title, one-line summary) that expands/collapses a
    `.content` frame. Keeps long dialogs short: collapsed sections still show
    their current state through the summary."""

    def __init__(self, master, title, summary="", expanded=False, bg=COLOR_BG, fg="#e6e6e6", sub="#8a8a8a"):
        super().__init__(master, bg=bg)
        self._expanded = False
        header = tk.Frame(self, bg=bg, cursor="hand2")
        header.pack(fill="x")
        self._arrow = tk.Label(header, text="▸", bg=bg, fg=sub, width=2)
        self._arrow.pack(side="left")
        tk.Label(header, text=title, bg=bg, fg=fg, font=("Segoe UI", 9, "bold")).pack(side="left")
        self._summary = tk.StringVar(value=summary)
        tk.Label(header, textvariable=self._summary, bg=bg, fg=sub, font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))
        self.content = tk.Frame(self, bg=bg)
        for w in [header] + list(header.winfo_children()):
            w.bind("<Button-1>", lambda e: self.toggle())
        if expanded:
            self.toggle()

    def set_summary(self, text):
        self._summary.set(text)

    def toggle(self):
        self._expanded = not self._expanded
        self._arrow.configure(text="▾" if self._expanded else "▸")
        if self._expanded:
            self.content.pack(fill="x", padx=(22, 0), pady=(4, 6))
        else:
            self.content.pack_forget()

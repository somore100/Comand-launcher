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

    def _on_yscroll(self, first, last):
        self.scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        elif not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y")

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        # Canvas has no natural height; track the content so the dialog can size to it.
        self.canvas.configure(height=self.inner.winfo_reqheight())

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
    dialog.minsize(min(width, 360), min(height, 240))

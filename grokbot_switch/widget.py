from pathlib import Path
import tkinter as tk

# ----------------------------------------------------------------------
# Icon handling
# ----------------------------------------------------------------------
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_CANDIDATES = [
    _ASSETS / "icon.png",
]

def icon_path() -> Path | None:
    """Return the first existing icon file, or None."""
    for p in ICON_CANDIDATES:
        if p.is_file():
            return p
    return None

# ----------------------------------------------------------------------
# Colour palette
# ----------------------------------------------------------------------
GREEN_BG = "#E8F8EE"
GREEN_FG = "#0B5C2E"
GREEN_DOT = "#12B76A"

RED_BG = "#FDECEA"
RED_FG = "#8B1A12"
RED_DOT = "#E03E2F"

ACCENT = "#0067C0"
ACCEPT_BG = "#0F9D58"

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------
def _no_taskbar(win: tk.Toplevel) -> None:
    """Make a window behave like a toast / tool-window (no task-bar entry)."""
    try:
        win.overrideredirect(True)
        win.attributes("-topmost", True)
    except Exception:
        pass
    try:
        win.wm_attributes("-toolwindow", True)
    except Exception:
        pass


def _sized_icon_path(size: int) -> Path | None:
    """Prefer a pre-resized icon so Windows does not need Pillow."""
    exact = _ASSETS / f"icon-{int(size)}.png"
    if exact.is_file():
        return exact
    # nearest pre-sized file at or above the requested size
    sized = []
    for p in _ASSETS.glob("icon-*.png"):
        try:
            n = int(p.stem.rsplit("-", 1)[1])
        except Exception:
            continue
        sized.append((n, p))
    at_least = [pair for pair in sized if pair[0] >= size]
    if at_least:
        return min(at_least, key=lambda pair: pair[0])[1]
    if sized:
        return max(sized, key=lambda pair: pair[0])[1]
    return icon_path()


def _load_icon(owner: tk.Misc, size: int) -> tk.PhotoImage | None:
    """Load the app icon and down-scale it to roughly *size* pixels."""
    path = _sized_icon_path(size) or icon_path()
    if not path:
        return None
    try:
        img = tk.PhotoImage(file=str(path), master=owner)
        w = int(img.width())
        if w > size * 2:
            factor = max(1, w // size)
            img = img.subsample(factor, factor)
        return img
    except Exception:
        return None

# ----------------------------------------------------------------------
# Public UI helpers
# ----------------------------------------------------------------------
def show_toast(message: str, ms: int = 4000) -> None:
    """Show a transient toast-style notification."""
    created = False
    root = getattr(tk, "_default_root", None)
    if root is None:
        root = tk.Tk()
        created = True
        root.withdraw()

    toast = tk.Toplevel(root)
    _no_taskbar(toast)
    toast.configure(bg="#222222")

    tk.Label(
        toast,
        text=message,
        fg="white",
        bg="#222222",
        font=("Segoe UI", 11),
        padx=16,
        pady=12,
        wraplength=320,
        justify="left",
    ).pack()

    toast.update_idletasks()
    sw, sh = toast.winfo_screenwidth(), toast.winfo_screenheight()
    w, h = toast.winfo_reqwidth(), toast.winfo_reqheight()
    toast.geometry(f"{w}x{h}+{sw-w-24}+{sh-h-80}")

    def close() -> None:
        try:
            toast.destroy()
        finally:
            if created:
                try:
                    root.destroy()
                except Exception:
                    pass

    toast.after(ms, close)

    if created:
        root.mainloop()


def show_permission_popup(
    bot: str,
    job: str,
    minutes,
    auto_allow_minutes: int = 5,
) -> str:
    """Blocking permission dialog. Returns 'accept', 'decline' or 'auto-accept'."""
    result: dict[str, str | None] = {"value": None}
    root = tk.Tk()
    root.withdraw()

    win = tk.Toplevel(root)
    _no_taskbar(win)
    win.title("Permission needed")
    win.configure(bg="#FCFCFC")

    outer = tk.Frame(win, bg="#FCFCFC", padx=22, pady=16)
    outer.pack(fill="both", expand=True)

    tk.Label(
        outer,
        text="Permission needed",
        bg="#FCFCFC",
        fg="#2B2B2B",
        font=("Segoe UI", 10, "bold"),
        anchor="w",
    ).pack(fill="x")

    icon = _load_icon(win, 64)
    if icon:
        lbl = tk.Label(outer, image=icon, bg="#FCFCFC")
        lbl.image = icon  # keep a reference
        lbl.pack(pady=(12, 8))

    tk.Label(
        outer,
        text=f"{bot} wants to use this PC",
        bg="#FCFCFC",
        fg="#161616",
        font=("Segoe UI", 13, "bold"),
        wraplength=340,
    ).pack(pady=(4, 0))

    job_line = f"Job: {job}" if job else ""
    try:
        mins = int(minutes or 0)
    except Exception:
        mins = 0
    if mins:
        job_line = (job_line + f" (about {mins} min)").strip()
    if job_line:
        tk.Label(
            outer,
            text=job_line,
            bg="#FCFCFC",
            fg="#5A5A5A",
            font=("Segoe UI", 10),
        ).pack(pady=(4, 12))

    btns = tk.Frame(outer, bg="#FCFCFC")
    btns.pack(fill="x")

    countdown = tk.Label(
        outer,
        text="",
        bg="#FCFCFC",
        fg="#6D6D6D",
        font=("Segoe UI", 10),
    )
    countdown.pack(pady=(12, 0))

    remaining = {"s": int(float(auto_allow_minutes) * 60)}

    def finish(val: str) -> None:
        if result["value"] is not None:
            return
        result["value"] = val
        try:
            win.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def tick() -> None:
        if result["value"] is not None:
            return
        s = remaining["s"]
        if s <= 0:
            finish("auto-accept")
            return
        m, sec = divmod(s, 60)
        countdown.config(text=f"Auto-accept in {m}:{sec:02d}")
        remaining["s"] -= 1
        win.after(1000, tick)

    tk.Button(
        btns,
        text="Decline",
        command=lambda: finish("decline"),
        bg=RED_BG,
        fg=RED_FG,
        relief="flat",
        font=("Segoe UI", 11, "bold"),
        padx=16,
        pady=8,
    ).pack(side="left", expand=True, fill="x", padx=(0, 6))

    tk.Button(
        btns,
        text="Accept",
        command=lambda: finish("accept"),
        bg=ACCEPT_BG,
        fg="white",
        relief="flat",
        font=("Segoe UI", 11, "bold"),
        padx=16,
        pady=8,
    ).pack(side="left", expand=True, fill="x", padx=(6, 0))

    tick()
    win.update_idletasks()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    w, h = max(win.winfo_reqwidth(), 400), win.winfo_reqheight()
    win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 40}")

    root.mainloop()
    return result["value"] or "decline"

# ----------------------------------------------------------------------
# Settings / pill polish
# ----------------------------------------------------------------------
PAGE_BG = "#F3F3F3"
CARD_BG = "#FFFFFF"
TEXT = "#1A1A1A"
TEXT_SECONDARY = "#5A5A5A"
TEXT_MUTED = "#6D6D6D"
LINE = "#E6E6E6"
TOGGLE_OFF = "#C2C2C2"
NOTE_BG = "#EEF4FB"
NOTE_FG = "#1B3A5A"
NOTE_BD = "#D3E3F5"
TRANSPARENT_KEY = "#010203"


def draw_rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs) -> int:
    """Draw a rounded rectangle as a polygon of short circular-arc segments."""
    import math

    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    radius = max(0.0, min(float(radius), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    if radius <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)

    points: list[float] = []

    def corner(cx, cy, start_deg, end_deg, steps=9):
        for i in range(steps + 1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

    corner(x1 + radius, y1 + radius, 180, 270)
    corner(x2 - radius, y1 + radius, 270, 360)
    corner(x2 - radius, y2 - radius, 0, 90)
    corner(x1 + radius, y2 - radius, 90, 180)
    return canvas.create_polygon(points, smooth=False, **kwargs)


def apply_chroma_key(win: tk.Misc, color: str = TRANSPARENT_KEY) -> bool:
    """Punch out *color* so rounded corners can be transparent. Windows mainly."""
    try:
        win.wm_attributes("-transparentcolor", color)
        return True
    except Exception:
        try:
            win.attributes("-transparentcolor", color)
            return True
        except Exception:
            return False


class ToggleSwitch(tk.Canvas):
    """A 40x20 iOS/Windows-style toggle drawn with Canvas only."""

    WIDTH = 40
    HEIGHT = 20

    def __init__(self, master, value: bool = False, command=None, **kw):
        bg = PAGE_BG
        try:
            bg = master.cget("bg")
        except Exception:
            pass
        kw.setdefault("width", self.WIDTH)
        kw.setdefault("height", self.HEIGHT)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        kw.setdefault("cursor", "hand2")
        kw.setdefault("bg", bg)
        super().__init__(master, **kw)
        self._value = bool(value)
        self._command = command
        self._track = None
        self._knob = None
        self._draw()
        self.bind("<Button-1>", self._on_click)

    def _knob_box(self, on: bool):
        r = 8
        cy = self.HEIGHT / 2
        cx = 30 if on else 10
        return (cx - r, cy - r, cx + r, cy + r)

    def _draw(self):
        self.delete("all")
        fill = ACCENT if self._value else TOGGLE_OFF
        self._track = draw_rounded_rect(
            self, 0, 0, self.WIDTH, self.HEIGHT, 10, fill=fill, outline=""
        )
        self._knob = self.create_oval(*self._knob_box(self._value), fill="#FFFFFF", outline="")

    def _on_click(self, _event=None):
        self.set(not self._value, notify=True)

    def get(self) -> bool:
        return self._value

    def set(self, value: bool, notify: bool = False) -> None:
        value = bool(value)
        changed = value != self._value
        if changed:
            self._value = value
            self._draw()
        if notify and changed and self._command:
            self._command(self._value)


class RoundedCard(tk.Frame):
    """A white rounded card; pack children into ``.body``."""

    def __init__(self, master, width: int = 400, radius: int = 10, **kw):
        kw.setdefault("bg", PAGE_BG)
        super().__init__(master, **kw)
        self._width = int(width)
        self._radius = int(radius)
        self._pad = 2
        self._canvas = tk.Canvas(
            self, bg=PAGE_BG, highlightthickness=0, bd=0, width=self._width, height=48
        )
        self._canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self._canvas, bg=CARD_BG)
        self._win = self._canvas.create_window(self._pad, self._pad, window=self.body, anchor="nw")
        self._rect = None
        self.body.bind("<Configure>", self._fit)

    def _fit(self, _event=None):
        self.body.update_idletasks()
        bw = max(self._width - 2 * self._pad, self.body.winfo_reqwidth())
        bh = max(24, self.body.winfo_reqheight())
        w = bw + 2 * self._pad
        h = bh + 2 * self._pad
        self._canvas.config(width=w, height=h)
        if self._rect is not None:
            self._canvas.delete(self._rect)
        self._rect = draw_rounded_rect(
            self._canvas,
            0.5,
            0.5,
            w - 0.5,
            h - 0.5,
            self._radius,
            fill=CARD_BG,
            outline="#E8E8E8",
            width=1,
        )
        self._canvas.tag_lower(self._rect)
        self._canvas.coords(self._win, self._pad, self._pad)
        self._canvas.itemconfigure(self._win, width=bw)


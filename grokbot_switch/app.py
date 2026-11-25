from pathlib import Path
import os, sys, threading, shlex
from datetime import datetime
from grokbot_switch.config import default_appdata_dir, load_config, save_config, DAY_NAMES
from grokbot_switch.schedule_edit import (
    add_schedule_rule,
    remove_schedule_rule,
    format_days,
    format_time_range,
    format_rule_line,
    parse_time_input,
)
from grokbot_switch.minimize_ui import (
    MINI_SIZE,
    tooltip_text,
    in_box,
    pill_anchor,
    pill_from_dot,
)
from grokbot_switch.clock import SystemClock
from grokbot_switch.idle import WindowsIdleProvider, FakeIdleProvider
from grokbot_switch.rules import decide
from grokbot_switch.status import write_status
from grokbot_switch.lease import apply_yield, heartbeat_status, release_lease, create_lease
from grokbot_switch.ipc import IpcServer
import grokbot_switch.startup as startup
from grokbot_switch.widget import (
    show_toast,
    show_permission_popup,
    _load_icon,
    _no_taskbar,
    apply_chroma_key,
    draw_rounded_rect,
    ToggleSwitch,
    RoundedCard,
    GREEN_BG,
    GREEN_FG,
    GREEN_DOT,
    RED_BG,
    RED_FG,
    RED_DOT,
    ACCENT,
    PAGE_BG,
    CARD_BG,
    TEXT,
    TEXT_SECONDARY,
    TEXT_MUTED,
    LINE,
    NOTE_BG,
    NOTE_FG,
    NOTE_BD,
    TRANSPARENT_KEY,
)
import tkinter as tk


class SwitchApp:
    def __init__(self, appdata_dir=None):
        self.appdata = Path(appdata_dir) if appdata_dir else default_appdata_dir()
        self.appdata.mkdir(parents=True, exist_ok=True)
        self.config_path = self.appdata / "config.json"
        self.config = load_config(self.config_path)
        self.clock = SystemClock()
        try:
            if os.name == "nt":
                self.idle = WindowsIdleProvider()
            else:
                raise NotImplementedError("Windows idle provider is unavailable")
        except Exception:
            self.idle = FakeIdleProvider(self.clock, 999)
        self.manual = None
        self.last_state = None
        self.root = None
        self._ipc = None
        self.ipc_port = None
        self._drag = {"x": 0, "y": 0, "moved": False}
        self._pill_widgets = {}
        self._icon_img = None
        self._settings_win = None
        self._add_time_win = None
        self._toggles = {}
        self._last_decision = None
        self._mini_icon = None

    def _decision(self):
        now = self.clock.now()
        sec = self.idle.seconds_idle()
        d = decide(now, sec, self.config, manual=self.manual, last_state=self.last_state)
        self.last_state = d.state
        if d.reason != "manual":
            self.manual = None
        return d, now, sec

    def _write_status(self, d, now, sec):
        write_status(
            self.appdata,
            d,
            self.idle.last_input_time(now),
            sec,
            extra={"ipc_port": self.ipc_port or self.config.get("ipc_port")},
            now=now,
        )

    def _apply_yields(self, now):
        grace = int(self.config.get("yield_grace_seconds", 2))
        results = apply_yield(self.appdata, now, self.idle.last_input_time(now), grace_seconds=grace)
        for r in results:
            self.manual = None
            self.last_state = "dnd"
            if r.toast and self.root:
                self.root.after(0, lambda m=r.toast: show_toast(m))
        return results

    def toggle_manual(self):
        d, now, sec = self._decision()
        new = "dnd" if d.state == "available" else "available"
        self.manual = {"state": new, "set_at": now, "seconds_idle_at_set": sec}
        self._refresh()

    def _refresh(self):
        now = self.clock.now()
        self._apply_yields(now)
        d, now, sec = self._decision()
        self._write_status(d, now, sec)
        render = getattr(self, "_render_pill", None)
        if callable(render):
            render(d)

    def handle_ipc(self, request: dict) -> dict:
        typ = request.get("type")
        if typ == "status":
            d, now, sec = self._decision()
            return {"ok": True, "state": d.state, "reason": d.reason, "reason_text": d.reason_text}
        if typ == "heartbeat":
            ok, result = heartbeat_status(self.appdata, request.get("lease_id") or "")
            return {"allow": ok, "result": result, "lease_id": request.get("lease_id")}
        if typ == "release":
            release_lease(self.appdata, request.get("lease_id") or "", self.clock.now())
            return {"allow": False, "result": "released", "lease_id": request.get("lease_id")}
        if typ == "check":
            return self._handle_check(request)
        return {"ok": False, "allow": False, "result": "error", "reason": "unknown request"}

    def _handle_check(self, request: dict) -> dict:
        d, now, sec = self._decision()
        bot = request.get("bot") or "A bot"
        job = request.get("job") or ""
        minutes = request.get("minutes") or 0
        if d.state == "dnd":
            return {"allow": False, "result": "dnd", "reason": d.reason_text}
        if not self.config.get("ask_before_use", True):
            lease = create_lease(self.appdata, bot, job, minutes, now, self.idle.last_input_time(now))
            return {"allow": True, "result": "accept", "lease_id": lease["lease_id"]}
        ev = threading.Event()
        box = {}

        def ask():
            try:
                box["v"] = show_permission_popup(
                    bot,
                    job,
                    minutes,
                    self.config.get("auto_allow_minutes", 5),
                )
            except Exception as exc:
                box["v"] = "error"
                box["e"] = str(exc)
            ev.set()

        if self.root:
            self.root.after(0, ask)
        else:
            ask()
        ev.wait(timeout=int((self.config.get("auto_allow_minutes") or 5) * 60) + 30)
        result = box.get("v") or "decline"
        if result in ("accept", "auto-accept"):
            now2 = self.clock.now()
            lease = create_lease(
                self.appdata,
                bot,
                job,
                minutes,
                now2,
                self.idle.last_input_time(now2),
            )
            return {"allow": True, "result": result, "lease_id": lease["lease_id"]}
        if result == "error":
            return {"allow": False, "result": "error", "reason": box.get("e", "popup failed")}
        return {"allow": False, "result": result}


    def _ui_font(self, size, weight="normal"):
        family = "Segoe UI" if os.name == "nt" else "Inter"
        if weight == "normal":
            return (family, size)
        return (family, size, weight)

    def _default_position(self) -> tuple[int, int]:
        pos = self.config.get("widget_position")
        if isinstance(pos, dict):
            try:
                return (int(pos["x"]), int(pos["y"]))
            except Exception:
                pass
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pill_w, pill_h, margin, taskbar_h = 248, 52, 16, 48
        x = screen_w - pill_w - margin
        y = screen_h - taskbar_h - pill_h - margin
        return (x, y)

    def _save_position(self):
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            if self._is_minimized():
                origin = (self._pill_widgets or {}).get("dot_screen")
                if origin:
                    x, y = origin
                w = int((self._pill_size or {}).get("w") or 248)
                x, y = pill_from_dot(x, y, w, 52)
            self.config["widget_position"] = {"x": int(x), "y": int(y)}
            save_config(self.config_path, self.config)
        except Exception:
            pass

    def _is_minimized(self) -> bool:
        return bool(self.config.get("widget_minimized"))

    def _set_minimized(self, value: bool):
        value = bool(value)
        if value and not self._is_minimized():
            self._save_position()
        self.config["widget_minimized"] = value
        try:
            save_config(self.config_path, self.config)
        except Exception:
            pass
        self._refresh()

    def _hit_minimize(self, event) -> bool:
        return in_box(event.x, event.y, (self._pill_widgets or {}).get("min_box"))

    def _show_mini_tooltip(self, _event=None):
        if not self._is_minimized():
            return
        self._pill_widgets["tooltip_on"] = True
        if self._last_decision is not None:
            self._render_pill(self._last_decision)

    def _hide_mini_tooltip(self, _event=None):
        if not (self._pill_widgets or {}).get("tooltip_on"):
            return
        self._pill_widgets["tooltip_on"] = False
        if self._is_minimized() and self._last_decision is not None:
            self._render_pill(self._last_decision)

    def _show_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Exit", command=self.quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _build_pill(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.wm_attributes("-toolwindow", True)
        except Exception:
            pass
        self._chroma = apply_chroma_key(self.root, TRANSPARENT_KEY)
        self.root.configure(bg=TRANSPARENT_KEY)
        x, y = self._default_position()
        # Extra height leaves room for the auto-DND note chip under the pill.
        self._pill_size = {"w": 248, "h": 52, "note_h": 26, "gap": 6}
        total_h = 52 + 6 + 26
        self.root.geometry(f"248x{total_h}+{x}+{y}")

        canvas = tk.Canvas(
            self.root,
            width=248,
            height=total_h,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self._icon_img = _load_icon(self.root, 28)
        self._mini_icon = _load_icon(self.root, 18)
        self._pill_widgets = {"canvas": canvas, "chroma": self._chroma, "tooltip_on": False}
        self._bind_pill_canvas(canvas)
        # first paint; _refresh/_render_pill will paint the real state shortly
        class _Boot:
            state = "available"
            reason = "default"
        self._render_pill(_Boot())

    def _bind_pill_canvas(self, canvas):
        canvas.bind("<ButtonPress-1>", self._on_pill_press)
        canvas.bind("<B1-Motion>", self._on_drag_motion)
        canvas.bind("<ButtonRelease-1>", self._on_pill_release)
        canvas.bind("<Button-3>", self._show_context_menu)
        canvas.bind("<Enter>", self._show_mini_tooltip)
        canvas.bind("<Leave>", self._hide_mini_tooltip)

    def _hit_gear(self, event) -> bool:
        return in_box(event.x, event.y, (self._pill_widgets or {}).get("gear_box"))

    def _on_pill_press(self, event):
        if self._is_minimized():
            self._hide_mini_tooltip()
        self._drag["gear"] = self._hit_gear(event)
        self._drag["minimize"] = (not self._drag["gear"]) and self._hit_minimize(event)
        self._on_drag_start(event)

    def _on_pill_release(self, event):
        moved = bool(self._drag.get("moved"))
        if moved:
            self._save_position()
            return
        if self._is_minimized():
            self._set_minimized(False)
            return
        if self._drag.get("gear"):
            self.open_settings()
            return
        if self._drag.get("minimize"):
            self._set_minimized(True)
            return
        self.toggle_manual()

    def _on_drag_start(self, event):
        self._drag["x"] = event.x_root
        self._drag["y"] = event.y_root
        self._drag["win_x"] = self.root.winfo_x()
        self._drag["win_y"] = self.root.winfo_y()
        self._drag["moved"] = False
        origin = (self._pill_widgets or {}).get("dot_screen")
        if origin:
            self._drag["dot_off"] = (origin[0] - self._drag["win_x"], origin[1] - self._drag["win_y"])
        else:
            self._drag["dot_off"] = (0, 0)

    def _on_drag_motion(self, event):
        dx = event.x_root - self._drag["x"]
        dy = event.y_root - self._drag["y"]
        new_x = self._drag["win_x"] + dx
        new_y = self._drag["win_y"] + dy
        self.root.geometry(f"+{new_x}+{new_y}")
        if abs(dx) > 4 or abs(dy) > 4:
            self._drag["moved"] = True
        if self._is_minimized() and self._pill_widgets is not None:
            # The window top-left may include tooltip padding; keep the dot's
            # screen origin in lockstep with the drag.
            ox, oy = self._drag.get("dot_off", (0, 0))
            self._pill_widgets["dot_screen"] = (new_x + ox, new_y + oy)

    def _place_root(self, width, height, x=None, y=None):
        self.root.configure(bg=TRANSPARENT_KEY)
        if x is None or y is None:
            geo = self.root.geometry()
            if "+" in geo:
                # keep current top-left
                self.root.geometry(f"{int(width)}x{int(height)}{geo[geo.find('+'):]}")
                return
            x, y = self._default_position()
        self.root.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")

    def _render_pill(self, decision):
        canvas = (self._pill_widgets or {}).get("canvas")
        if canvas is None:
            return
        self._last_decision = decision
        if self._is_minimized():
            self._render_mini(decision)
            return
        state = getattr(decision, "state", "available")
        reason = getattr(decision, "reason", None)
        if state == "available":
            fill, fg, dot_color = GREEN_BG, GREEN_FG, GREEN_DOT
            label = "Available"
        else:
            fill, fg, dot_color = RED_BG, RED_FG, RED_DOT
            label = "Do Not Disturb"

        font = self._ui_font(12, "bold")
        probe = canvas.create_text(0, 0, text=label, font=font, anchor="nw")
        x1, y1, x2, y2 = canvas.bbox(probe)
        canvas.delete(probe)
        text_w = max(0, x2 - x1)
        # padding: 18 + 11(dot) + 11 + 26(icon) + 11 + text + 8 + 32(min) + 4 + 34(gear) + 8
        width = int(18 + 11 + 11 + 26 + 11 + text_w + 8 + 32 + 4 + 34 + 8)
        width = max(248, width)
        height = 52
        radius = 26
        gap, note_h = 6, 26
        show_note = reason == "active"
        total_h = height + (gap + note_h if show_note else 0)
        win_h = max(total_h, height + gap + note_h)
        canvas.config(width=width, height=win_h)
        # When restoring, place the pill at the remembered top-left.
        px, py = self._default_position()
        self._place_root(width, win_h, px, py)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, win_h, fill=TRANSPARENT_KEY, outline="")

        draw_rounded_rect(
            canvas, 0.5, 0.5, width - 0.5, height - 0.5, radius,
            fill=fill, outline="#FFFFFF", width=1, tags=("pill",),
        )

        dx, dy, dr = 18 + 5, height / 2, 5.5
        canvas.create_oval(dx - dr, dy - dr, dx + dr, dy + dr, fill=dot_color, outline=dot_color, tags=("pill",))

        ix = 18 + 11 + 11
        if self._icon_img is not None:
            canvas.create_image(ix + 13, height / 2, image=self._icon_img, tags=("pill",))
        tx = ix + 26 + 11
        canvas.create_text(tx, height / 2, text=label, fill=fg, font=font, anchor="w", tags=("pill",))

        btn_fill = "#F7FBF8" if state == "available" else "#FDF6F5"
        # Gear at the far right, minimize button immediately to its left.
        gx2, gy = width - 8, height / 2
        gx1 = gx2 - 34
        gcx, gcy, gcr = (gx1 + gx2) / 2, gy, 17
        canvas.create_oval(gcx - gcr, gcy - gcr, gcx + gcr, gcy + gcr, fill=btn_fill, outline="", tags=("gear",))
        canvas.create_text(gcx, gcy, text="⚙", fill=fg, font=self._ui_font(11), tags=("gear",))
        self._pill_widgets["gear_box"] = (gcx - gcr, gcy - gcr, gcx + gcr, gcy + gcr)

        mx2 = gx1 - 4
        mx1 = mx2 - 32
        mcx, mcy, mcr = (mx1 + mx2) / 2, gy, 16
        canvas.create_oval(mcx - mcr, mcy - mcr, mcx + mcr, mcy + mcr, fill=btn_fill, outline="", tags=("min",))
        canvas.create_line(mcx - 5, mcy, mcx + 5, mcy, fill=fg, width=2, capstyle=tk.ROUND, tags=("min",))
        self._pill_widgets["min_box"] = (mcx - mcr, mcy - mcr, mcx + mcr, mcy + mcr)
        self._pill_widgets["tooltip_on"] = False
        self._pill_widgets["size"] = (width, height)

        if show_note:
            note = "Auto: you're using this PC"
            nf = self._ui_font(9)
            probe = canvas.create_text(0, 0, text=note, font=nf, anchor="nw")
            nx1, ny1, nx2, ny2 = canvas.bbox(probe)
            canvas.delete(probe)
            nw, nh = (nx2 - nx1) + 20, 24
            nx = max(0, width - nw - 6)
            ny = height + gap
            draw_rounded_rect(
                canvas, nx, ny, nx + nw, ny + nh, 10,
                fill="#4A3F3F", outline="#6A5F5F", width=1, tags=("note",),
            )
            canvas.create_text(nx + nw / 2, ny + nh / 2, text=note, fill="#FFFFFF", font=nf, tags=("note",))

        self._pill_size = {"w": width, "h": height}

    def _render_mini(self, decision):
        canvas = self._pill_widgets["canvas"]
        state = getattr(decision, "state", "available")
        ring = GREEN_DOT if state == "available" else RED_DOT
        fill = GREEN_BG if state == "available" else RED_BG
        tip = tooltip_text(state)
        tip_on = bool(self._pill_widgets.get("tooltip_on"))

        pill_w = int((self._pill_size or {}).get("w") or 248)
        pill_h = 52
        px, py = self._default_position()
        dot_x, dot_y = pill_anchor(px, py, pill_w, pill_h, MINI_SIZE)

        tip_w = tip_h = 0
        if tip_on:
            probe = canvas.create_text(0, 0, text=tip, font=self._ui_font(9), anchor="nw")
            bx1, by1, bx2, by2 = canvas.bbox(probe)
            canvas.delete(probe)
            tip_w = (bx2 - bx1) + 20
            tip_h = (by2 - by1) + 14

        pad = 6
        gap = 8
        win_w = max(MINI_SIZE, int(tip_w) + pad) if tip_on else MINI_SIZE
        win_h = MINI_SIZE + (int(tip_h) + gap if tip_on else 0)
        # Keep the 28px dot pinned at dot_x,dot_y; grow the window up and left.
        win_x = dot_x + MINI_SIZE - win_w
        win_y = dot_y + MINI_SIZE - win_h
        canvas.config(width=win_w, height=win_h)
        self._place_root(win_w, win_h, win_x, win_y)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, win_w, win_h, fill=TRANSPARENT_KEY, outline="")

        # Dot is at the bottom-right of this window.
        dx0, dy0 = win_w - MINI_SIZE, win_h - MINI_SIZE
        # soft halo
        canvas.create_oval(dx0 - 2, dy0 - 2, dx0 + MINI_SIZE + 2, dy0 + MINI_SIZE + 2, outline=ring, width=1, tags=("mini",))
        canvas.create_oval(dx0 + 1, dy0 + 1, dx0 + MINI_SIZE - 1, dy0 + MINI_SIZE - 1, fill=fill, outline=ring, width=2, tags=("mini",))
        if self._mini_icon is not None:
            canvas.create_image(dx0 + MINI_SIZE / 2, dy0 + MINI_SIZE / 2, image=self._mini_icon, tags=("mini",))
        elif self._icon_img is not None:
            canvas.create_image(dx0 + MINI_SIZE / 2, dy0 + MINI_SIZE / 2, image=self._icon_img, tags=("mini",))

        if tip_on and tip_w and tip_h:
            tx = max(0, win_w - tip_w)
            ty = 0
            draw_rounded_rect(
                canvas, tx, ty, tx + tip_w, ty + tip_h, 8,
                fill="#2C2C2C", outline="", tags=("tip",),
            )
            canvas.create_text(
                tx + tip_w / 2, ty + tip_h / 2, text=tip, fill="#FFFFFF",
                font=self._ui_font(9), tags=("tip",),
            )
            # caret pointing at the dot
            caret_x = dx0 + MINI_SIZE / 2
            canvas.create_polygon(
                caret_x - 6, ty + tip_h,
                caret_x + 6, ty + tip_h,
                caret_x, ty + tip_h + 6,
                fill="#2C2C2C", outline="", tags=("tip",),
            )

        self._pill_widgets["gear_box"] = None
        self._pill_widgets["min_box"] = None
        self._pill_widgets["dot_screen"] = (dot_x, dot_y)
        self._pill_widgets["size"] = (MINI_SIZE, MINI_SIZE)

    def open_settings(self):
        if getattr(self, "_settings_win", None) is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.lift()
                    self._settings_win.focus_force()
                    return
            except Exception:
                self._settings_win = None

        win = tk.Toplevel(self.root)
        win.title("Switch settings")
        win.configure(bg=PAGE_BG)
        win.geometry("440x720")
        win.minsize(420, 640)
        self._settings_win = win
        self._toggles = {}
        self._setting_vars = {}

        outer = tk.Frame(win, bg=PAGE_BG)
        outer.pack(fill="both", expand=True, padx=16, pady=(14, 16))

        tk.Label(
            outer, text="Switch settings", bg=PAGE_BG, fg=TEXT,
            font=self._ui_font(16, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="Choose when this PC can be used by a bot.",
            bg=PAGE_BG, fg=TEXT_SECONDARY, font=self._ui_font(10),
            anchor="w", pady=4,
        ).pack(fill="x", pady=(0, 10))

        sched = RoundedCard(outer, width=400)
        sched.pack(fill="x", pady=(0, 10))
        tk.Label(
            sched.body, text="Schedule", bg=CARD_BG, fg=TEXT,
            font=self._ui_font(10, "bold"), anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))
        self._sched_body = tk.Frame(sched.body, bg=CARD_BG)
        self._sched_body.pack(fill="x")
        self._rebuild_schedule_list()

        card = RoundedCard(outer, width=400)
        card.pack(fill="x", pady=(0, 10))
        self._build_setting_rows(card.body)

        note = tk.Frame(outer, bg=NOTE_BG, highlightbackground=NOTE_BD, highlightthickness=1, bd=0)
        note.pack(fill="x", pady=(2, 0))
        inner = tk.Frame(note, bg=NOTE_BG)
        inner.pack(fill="x", padx=12, pady=10)
        tk.Label(inner, text="i", bg=NOTE_BG, fg=ACCENT, font=self._ui_font(10, "bold"), width=2, anchor="n").pack(side="left", padx=(0, 6))
        tk.Label(
            inner,
            text="The schedule always comes first. If you set Do Not Disturb for a time of day, it stays that way even when the PC is idle.",
            bg=NOTE_BG, fg=NOTE_FG, font=self._ui_font(9), wraplength=350, justify="left", anchor="w",
        ).pack(side="left", fill="x", expand=True)

        win.update_idletasks()
        needed = outer.winfo_reqheight() + 32
        win.geometry(f"440x{max(560, min(int(needed), 780))}")

        def _close():
            add = getattr(self, "_add_time_win", None)
            self._add_time_win = None
            if add is not None:
                try:
                    add.destroy()
                except Exception:
                    pass
            self._settings_win = None
            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", _close)

    def _rebuild_schedule_list(self):
        body = getattr(self, "_sched_body", None)
        if body is None:
            return
        for child in body.winfo_children():
            child.destroy()
        rules = list(self.config.get("schedule") or [])
        for i, rule in enumerate(rules):
            row = tk.Frame(body, bg=CARD_BG)
            row.pack(fill="x", padx=8, pady=6)
            mid = tk.Frame(row, bg=CARD_BG)
            mid.pack(side="left", fill="x", expand=True)
            tk.Label(
                mid, text=format_time_range(rule.get("start", ""), rule.get("end", "")),
                bg=CARD_BG, fg=TEXT, font=self._ui_font(10, "bold"), anchor="w",
            ).pack(fill="x")
            tk.Label(
                mid, text=format_days(rule.get("days") or []),
                bg=CARD_BG, fg=TEXT_MUTED, font=self._ui_font(9), anchor="w",
            ).pack(fill="x")
            state = rule.get("state")
            if state == "available":
                badge_bg, badge_fg, badge_txt = GREEN_BG, "#0B6B3A", "Available"
            else:
                badge_bg, badge_fg, badge_txt = RED_BG, RED_FG, "Do Not Disturb"
            right = tk.Frame(row, bg=CARD_BG)
            right.pack(side="right")
            tk.Label(
                right, text=badge_txt, bg=badge_bg, fg=badge_fg,
                font=self._ui_font(8, "bold"), padx=8, pady=3,
            ).pack(side="top", anchor="e")
            tk.Button(
                right, text="Remove", command=lambda idx=i: self._remove_schedule(idx),
                bg=CARD_BG, fg=TEXT_MUTED, bd=0, relief="flat", highlightthickness=0,
                font=self._ui_font(8), cursor="hand2", takefocus=0, activebackground=CARD_BG,
            ).pack(side="top", anchor="e", pady=(4, 0))

        tk.Button(
            body, text="+  Add time", command=self._open_add_time,
            bg=CARD_BG, fg=ACCENT, bd=0, relief="flat", highlightthickness=0,
            font=self._ui_font(10, "bold"), cursor="hand2", takefocus=0,
            activeforeground=ACCENT, activebackground=CARD_BG, anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 10))

    def _build_setting_rows(self, parent):
        rows = [
            (
                "auto_dnd_when_active",
                "Turn Do Not Disturb on when I'm using this PC",
                "The switch turns red as soon as you start typing or moving the mouse.",
                None,
            ),
            (
                "auto_available_after_idle",
                "Turn Available after idle for",
                "If you step away, the switch turns green again after this time.",
                ("idle_minutes", "minutes"),
            ),
            (
                "ask_before_use",
                "Ask me before a bot uses this PC",
                "A popup appears so you can accept or decline.",
                None,
            ),
            (
                "start_with_windows",
                "Start with Windows",
                "Open the switch when you sign in. Off by default.",
                None,
            ),
        ]
        for i, (key, title, hint, number) in enumerate(rows):
            if i:
                tk.Frame(parent, bg=LINE, height=1).pack(fill="x", padx=8)
            row = tk.Frame(parent, bg=CARD_BG)
            row.pack(fill="x", padx=12, pady=10)
            copy = tk.Frame(row, bg=CARD_BG)
            copy.pack(side="left", fill="x", expand=True)
            title_row = tk.Frame(copy, bg=CARD_BG)
            title_row.pack(fill="x")
            tk.Label(
                title_row, text=title, bg=CARD_BG, fg=TEXT,
                font=self._ui_font(10, "bold"), anchor="w", justify="left", wraplength=280,
            ).pack(side="left")
            if number and number[0] == "idle_minutes":
                self._mini_number(title_row, "idle_minutes")
                tk.Label(
                    title_row, text=number[1], bg=CARD_BG, fg=TEXT,
                    font=self._ui_font(10, "bold"),
                ).pack(side="left", padx=(0, 0))
            tk.Label(
                copy, text=hint, bg=CARD_BG, fg=TEXT_MUTED,
                font=self._ui_font(9), anchor="w", justify="left", wraplength=300,
            ).pack(fill="x", pady=(2, 0))
            toggle = ToggleSwitch(
                row,
                value=bool(self.config.get(key, False)),
                command=lambda v, k=key: self._on_setting_change(k, v),
            )
            toggle.pack(side="right", padx=(10, 0), pady=(2, 0))
            self._toggles[key] = toggle
            if key == "ask_before_use":
                sub = tk.Frame(parent, bg=CARD_BG)
                sub.pack(fill="x", padx=12, pady=(0, 10))
                tk.Label(
                    sub, text="If no answer, allow after", bg=CARD_BG, fg=TEXT,
                    font=self._ui_font(9),
                ).pack(side="left")
                self._mini_number(sub, "auto_allow_minutes")
                tk.Label(
                    sub, text="minutes", bg=CARD_BG, fg=TEXT, font=self._ui_font(9),
                ).pack(side="left")

    def _mini_number(self, parent, key):
        var = tk.StringVar(value=str(int(self.config.get(key, 1))))
        self._setting_vars[key] = var

        def commit(_event=None, k=key, sv=var):
            try:
                val = int(str(sv.get()).strip())
                if val < 1:
                    raise ValueError
                self._on_setting_change(k, val)
            except Exception:
                sv.set(str(int(self.config.get(k, 1))))

        entry = tk.Entry(
            parent, textvariable=var, width=3, justify="center",
            font=self._ui_font(10, "bold"), bd=1, relief="solid",
            highlightthickness=0, bg="#F3F3F3", fg=TEXT,
        )
        entry.pack(side="left", padx=6)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Return>", commit)
        return var

    def _format_rule(self, rule):
        return format_rule_line(rule)

    def _on_setting_change(self, key, value):
        previous = self.config.get(key)
        self.config[key] = value
        if key == "start_with_windows":
            try:
                startup.set_enabled(bool(value), self._startup_command())
            except Exception:
                self.config[key] = previous
                toggle = self._toggles.get(key)
                if toggle is not None:
                    try:
                        toggle.set(bool(previous), notify=False)
                    except Exception:
                        pass
                return
        try:
            save_config(self.config_path, self.config)
        except Exception:
            self.config[key] = previous
            return
        self._refresh()

    def _open_add_time(self):
        existing = getattr(self, "_add_time_win", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                self._add_time_win = None

        parent = self._settings_win or self.root
        win = tk.Toplevel(parent)
        win.title("Add time")
        win.configure(bg=PAGE_BG)
        win.geometry("420x380")
        win.resizable(False, False)
        try:
            win.transient(parent)
        except Exception:
            pass

        def _on_close():
            self._add_time_win = None
            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", _on_close)

        pad = tk.Frame(win, bg=PAGE_BG)
        pad.pack(fill="both", expand=True, padx=16, pady=14)

        tk.Label(pad, text="Add time", bg=PAGE_BG, fg=TEXT, font=self._ui_font(14, "bold"), anchor="w").pack(fill="x")
        tk.Label(pad, text="Days", bg=PAGE_BG, fg=TEXT, font=self._ui_font(10, "bold"), anchor="w").pack(fill="x", pady=(12, 4))

        labels = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}
        chk_vars = {}
        chk_frame = tk.Frame(pad, bg=PAGE_BG)
        chk_frame.pack(fill="x")
        for i, day in enumerate(DAY_NAMES):
            var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                chk_frame, text=labels[day], variable=var,
                bg=PAGE_BG, fg=TEXT, activebackground=PAGE_BG, activeforeground=TEXT,
                highlightthickness=0, bd=0, font=self._ui_font(9),
                selectcolor="#FFFFFF",
            ).grid(row=0, column=i, padx=3, sticky="w")
            chk_vars[day] = var

        times = tk.Frame(pad, bg=PAGE_BG)
        times.pack(fill="x", pady=(16, 0))
        tk.Label(times, text="Start", bg=PAGE_BG, fg=TEXT, font=self._ui_font(10, "bold")).grid(row=0, column=0, sticky="w")
        start_entry = tk.Entry(times, width=12, font=self._ui_font(10), bg="#FFFFFF")
        start_entry.grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(4, 0))
        tk.Label(times, text="End", bg=PAGE_BG, fg=TEXT, font=self._ui_font(10, "bold")).grid(row=0, column=1, sticky="w")
        end_entry = tk.Entry(times, width=12, font=self._ui_font(10), bg="#FFFFFF")
        end_entry.grid(row=1, column=1, sticky="w", pady=(4, 0))

        tk.Label(
            pad,
            text="Use 9:00 AM or 09:00. End must be later the same day.",
            bg=PAGE_BG, fg=TEXT_MUTED, font=self._ui_font(9), anchor="w", wraplength=380, justify="left",
        ).pack(fill="x", pady=(6, 12))

        state_var = tk.StringVar(value="dnd")
        state_row = tk.Frame(pad, bg=PAGE_BG)
        state_row.pack(fill="x")
        for value, label in (("dnd", "Do Not Disturb"), ("available", "Available")):
            tk.Radiobutton(
                state_row, text=label, variable=state_var, value=value,
                bg=PAGE_BG, fg=TEXT, activebackground=PAGE_BG, activeforeground=TEXT,
                selectcolor="#FFFFFF", highlightthickness=0, bd=0,
                font=self._ui_font(10),
            ).pack(side="left", padx=(0, 16))

        error_lbl = tk.Label(pad, text="", bg=PAGE_BG, fg="#C42B1C", font=self._ui_font(9), anchor="w", wraplength=380, justify="left")
        error_lbl.pack(fill="x", pady=(10, 0))

        btns = tk.Frame(pad, bg=PAGE_BG)
        btns.pack(fill="x", pady=(16, 0))
        tk.Button(
            btns, text="Save", command=self._submit_add_time,
            bg=ACCENT, fg="#FFFFFF", activebackground=ACCENT, activeforeground="#FFFFFF",
            bd=0, relief="flat", padx=16, pady=6, font=self._ui_font(10, "bold"), cursor="hand2",
        ).pack(side="right")
        tk.Button(
            btns, text="Cancel", command=_on_close,
            bg=PAGE_BG, fg=TEXT_SECONDARY, bd=0, relief="flat", padx=12, pady=6,
            font=self._ui_font(10), cursor="hand2", activebackground=PAGE_BG,
        ).pack(side="right", padx=(0, 8))

        self._add_time_win = win
        self._add_day_vars = chk_vars
        self._add_start = start_entry
        self._add_end = end_entry
        self._add_state = state_var
        self._add_error = error_lbl
        start_entry.focus_set()

    def _submit_add_time(self):
        err = getattr(self, "_add_error", None)

        def fail(message: str):
            if err is not None:
                err.configure(text=message)

        selected = [day for day in DAY_NAMES if self._add_day_vars[day].get()]
        if not selected:
            fail("Choose at least one day.")
            return
        start_time = parse_time_input(self._add_start.get())
        end_time = parse_time_input(self._add_end.get())
        if start_time is None or end_time is None:
            fail("Enter a start and end time like 9:00 AM or 09:00.")
            return
        if end_time <= start_time:
            fail("End has to be later than start on the same day.")
            return
        try:
            new_config = add_schedule_rule(
                self.config,
                {
                    "days": selected,
                    "start": start_time,
                    "end": end_time,
                    "state": self._add_state.get() or "dnd",
                },
            )
        except ValueError as exc:
            message = str(exc)
            if message == "no days":
                fail("Choose at least one day.")
            elif message == "bad time":
                fail("Enter a start and end time like 9:00 AM or 09:00.")
            elif message == "end not after start":
                fail("End has to be later than start on the same day.")
            else:
                fail(message or "That time could not be saved.")
            return
        self.config = new_config
        try:
            save_config(self.config_path, self.config)
        except Exception:
            fail("The time could not be saved.")
            return
        add = getattr(self, "_add_time_win", None)
        self._add_time_win = None
        if add is not None:
            try:
                add.destroy()
            except Exception:
                pass
        self._rebuild_schedule_list()
        self._refresh()

    def _remove_schedule(self, index: int):
        try:
            new_config = remove_schedule_rule(self.config, index)
        except IndexError:
            return
        self.config = new_config
        try:
            save_config(self.config_path, self.config)
        except Exception:
            return
        self._rebuild_schedule_list()
        self._refresh()

    def _startup_command(self) -> str:
        script = Path(__file__).resolve().parent.parent / "grokbot_switch_app.py"
        exe = sys.executable
        # Windows .bat files need double quotes, not POSIX shlex quotes.
        def q(s: str) -> str:
            return '"' + str(s).replace('"', '""') + '"'
        return f"{q(exe)} {q(script)}"

    def _start_ipc(self):
        base = int(self.config.get("ipc_port") or 47281)
        self._ipc = None
        self.ipc_port = None
        try:
            server = IpcServer(self.handle_ipc, port=base, appdata_dir=self.appdata)
            bound = server.start()
            self._ipc = server
            self.ipc_port = int(bound or server.port)
        except Exception:
            self._ipc = None
            self.ipc_port = None

    def _poll(self):
        try:
            if self.root is None:
                return
            self._refresh()
            self.root.after(1000, self._poll)
        except Exception:
            pass

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("GrokBot switch")
        self._build_pill()
        self._start_ipc()
        self._refresh()
        self._poll()
        try:
            self.root.deiconify()
        except Exception:
            pass
        try:
            self.root.mainloop()
        finally:
            self.quit()

    def quit(self):
        ipc = getattr(self, "_ipc", None)
        self._ipc = None
        if ipc is not None:
            try:
                ipc.stop()
            except Exception:
                pass
        for attr in ("_add_time_win", "_settings_win"):
            win = getattr(self, attr, None)
            setattr(self, attr, None)
            if win is not None:
                try:
                    win.destroy()
                except Exception:
                    pass
        root = getattr(self, "root", None)
        self.root = None
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoClicker PRO · TikTok
========================
Auto-clicker de escritorio para dar "me gusta" en TikTok sin quedarte
sin ratón ni teclado.

  * Velocidad de 1 a 10.000 clicks por minuto.
  * Modo "Ventana": el click se envía directamente a la ventana marcada
    (PostMessage). Tu cursor no se mueve y puedes seguir usando el PC.
  * Modo "Físico": mueve el cursor un instante y lo devuelve (respaldo
    para apps que ignoran los mensajes sintéticos).
  * PAUSA INTELIGENTE: si mueves el ratón o escribes, deja de clickear
    al momento y reanuda solo cuando dejas de usar el PC.
  * Atajos SIN hook de teclado:  T = iniciar/detener,  X = detener,
    F2 = marcar punto. Se leen por sondeo, así que no pueden bloquear
    ni retrasar tu teclado.
  * Hilo de clicks con prioridad baja y temporización precisa (no compite
    por la CPU con el ratón).

Sólo usa la librería estándar de Python: ctypes + tkinter.
"""

import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

APP_TITLE = "AutoClicker PRO · TikTok"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AutoClickerTikTok")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# --------------------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_SETFOCUS = 0x0007
MK_LBUTTON = 0x0001
GA_ROOT = 2

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.ScreenToClient.restype = wt.BOOL
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.ClientToScreen.restype = wt.BOOL
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND
user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                                        wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = wt.LPARAM
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wt.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = wt.BOOL
user32.VkKeyScanW.argtypes = [wt.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
kernel32.GetCurrentThread.restype = wt.HANDLE
kernel32.SetThreadPriority.argtypes = [wt.HANDLE, ctypes.c_int]
kernel32.SetThreadPriority.restype = wt.BOOL
kernel32.GetTickCount.restype = wt.DWORD


def set_dpi_aware():
    """Coordenadas en píxeles reales (sin escalado borroso)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def toplevel(hwnd):
    return user32.GetAncestor(hwnd, GA_ROOT) or hwnd


def describe_window(hwnd):
    title = window_title(toplevel(hwnd)) or window_class(toplevel(hwnd))
    return title or "ventana desconocida"


def idle_ms():
    """Milisegundos desde el último movimiento de ratón o tecla real."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        return (kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF
    return 10 ** 6


class Target:
    """Punto marcado: ventana destino + coordenadas de pantalla y de cliente."""

    def __init__(self, hwnd, sx, sy):
        self.hwnd = hwnd
        self.sx = int(sx)
        self.sy = int(sy)
        self.cx = 0
        self.cy = 0
        self.title = ""
        self.top_class = ""
        p = wt.POINT(self.sx, self.sy)
        user32.ScreenToClient(self.hwnd, ctypes.byref(p))
        self.cx, self.cy = p.x, p.y
        self._info()

    def _info(self):
        self.title = describe_window(self.hwnd)
        self.top_class = window_class(toplevel(self.hwnd))

    def sync_screen(self):
        """Recalcula el punto de pantalla según dónde esté ahora la ventana.

        El ancla real es el punto de la página (cliente): si arrastras o
        redimensionas la ventana, el click sigue yendo al mismo sitio.
        """
        p = wt.POINT(self.cx, self.cy)
        user32.ClientToScreen(self.hwnd, ctypes.byref(p))
        self.sx, self.sy = p.x, p.y

    def revalidate(self):
        """Si la ventana desapareció, busca la que haya ahora en ese punto."""
        if not user32.IsWindow(self.hwnd):
            hwnd = user32.WindowFromPoint(wt.POINT(self.sx, self.sy))
            if not hwnd:
                return False
            self.hwnd = hwnd
            p = wt.POINT(self.sx, self.sy)
            user32.ScreenToClient(self.hwnd, ctypes.byref(p))
            self.cx, self.cy = p.x, p.y
        self._info()
        self.sync_screen()
        return True

    def as_dict(self):
        return {"sx": self.sx, "sy": self.sy, "cls": self.top_class}


# --------------------------------------------------------------------------------------
# Clicks
# --------------------------------------------------------------------------------------
def post_click(hwnd, cx, cy):
    """Click 'invisible': llega a la ventana sin mover el cursor ni robarte el foco."""
    lp = ((int(cy) & 0xFFFF) << 16) | (int(cx) & 0xFFFF)
    ok = user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    ok = user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp) and ok
    ok = user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp) and ok
    return bool(ok)


def is_chromium(hwnd):
    """Chrome / Edge / WebView2: se auto-activan al recibir un click sintético."""
    cls = window_class(toplevel(hwnd)) + " " + window_class(hwnd)
    return "Chrome_WidgetWin" in cls or "RenderWidgetHost" in cls


SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002


def calm_focus(hwnd):
    """Avisa a Chrome de que 'ya tiene el foco' justo antes del click.

    Sin esto, Chrome se auto-activa al recibir el click sintético y te roba
    el teclado. Enviándolo de forma síncrona (SendMessageTimeout) Chrome ya
    lo ha procesado cuando llega el click, así que el foco real se queda
    donde tú estás trabajando.
    """
    top = toplevel(hwnd)
    res = ctypes.c_size_t()
    user32.SendMessageTimeoutW(top, WM_SETFOCUS, 0, 0,
                                SMTO_BLOCK | SMTO_ABORTIFHUNG, 30, ctypes.byref(res))


def _send_mouse(flags):
    inp = INPUT(type=INPUT_MOUSE)
    inp.u.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def physical_click(sx, sy, restore=True):
    """Click real (mueve el cursor un instante y lo devuelve)."""
    old = wt.POINT()
    user32.GetCursorPos(ctypes.byref(old))
    user32.SetCursorPos(int(sx), int(sy))
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    _send_mouse(MOUSEEVENTF_LEFTUP)
    if restore:
        user32.SetCursorPos(old.x, old.y)
    return True


class Clicker(threading.Thread):
    """Hilo de clicks: prioridad baja, temporización precisa y pausa por actividad."""

    def __init__(self, target, cpm, mode, restore, events,
                 pause_on_input=True, grace_ms=700):
        super().__init__(daemon=True)
        self.target = target
        self.cpm = max(1, min(10000, int(cpm)))
        self.mode = mode
        self.restore = restore
        self.events = events
        self.pause_on_input = bool(pause_on_input) and mode == "post"
        self.grace_ms = grace_ms
        self.clicks = 0
        self.failures = 0
        self.paused = False
        self.started_at = time.perf_counter()
        self._stop = threading.Event()
        self._no_pause_before = self.started_at + 1.0   # no pausar por la tecla T
        self._top = toplevel(target.hwnd)
        self._guard = (mode == "post") and is_chromium(target.hwnd)

    def stop(self):
        self._stop.set()

    def run(self):
        # prioridad algo por debajo de lo normal: no compite con ratón/teclado
        try:
            kernel32.SetThreadPriority(kernel32.GetCurrentThread(), -1)
        except Exception:
            pass

        interval = 60.0 / self.cpm
        target = self.target
        next_t = time.perf_counter()

        while not self._stop.is_set():
            # --- pausa inteligente: si estás usando el PC, no se clickea ---
            if self.pause_on_input and time.perf_counter() > self._no_pause_before:
                if idle_ms() < self.grace_ms:
                    if not self.paused:
                        self.paused = True
                    time.sleep(0.03)          # dormimos: no consume CPU ni GIL
                    next_t = time.perf_counter() + interval
                    continue
                if self.paused:
                    self.paused = False
            try:
                if self.mode == "post":
                    # si la ventana está en segundo plano, avisarla para que
                    # no se active y no te quite el foco al clickear
                    if self._guard and user32.GetForegroundWindow() != self._top:
                        calm_focus(target.hwnd)
                    ok = post_click(target.hwnd, target.cx, target.cy)
                else:
                    ok = physical_click(target.sx, target.sy, self.restore)
            except Exception:
                ok = False

            if ok:
                self.failures = 0
                self.clicks += 1
            else:
                self.failures += 1
                if self.failures > 40:
                    self.events.put(("lost", "La ventana destino ya no acepta clicks. "
                                             "Vuelve a marcar el punto con F2."))
                    return

            next_t += interval
            now = time.perf_counter()
            if next_t < now:              # vamos tarde: no acumular retraso
                next_t = now
            remain = next_t - now
            if remain > 0.0015:
                time.sleep(remain - 0.001)
            # últimos ~1 ms: espera activa cortísima (el sleep de Windows
            # se queda corto o largo y esto mantiene la velocidad exacta)
            while time.perf_counter() < next_t:
                if self._stop.is_set():
                    return


# --------------------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------------------
DEFAULTS = {
    "cpm": 300,
    "mode": "post",
    "restore": True,
    "start_key": "T",
    "stop_key": "X",
    "mark_key": "F2",
    "hotkeys": True,
    "pause_input": False,
    "point": None,
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in DEFAULTS:
                if k in data:
                    cfg[k] = data[k]
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def key_to_vk(key):
    """'T' -> VK_T, 'F2' -> VK_F2 ..."""
    if not key:
        return None
    key = key.strip().upper()
    if len(key) == 1 and key.isalnum():
        res = user32.VkKeyScanW(key)
        if res == -1:
            return None
        return res & 0xFF
    if key.startswith("F") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return 0x70 + n - 1
    if key == "ESPACIO":
        return 0x20
    return None


MODIFIER_VKS = (0x11, 0x12, 0x10, 0x5B, 0x5C)  # Ctrl, Alt, Shift, Win, Win


# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------
BG = "#0f1216"
CARD = "#181d24"
CARD2 = "#212932"
FG = "#eef2f6"
SUB = "#8b98a7"
ACCENT = "#fe2c55"
CYAN = "#25f4ee"
GREEN = "#22c55e"
AMBER = "#f0a020"
LINE = "#2a333e"

FONT = "Segoe UI"


def mk_card(parent, padx=16, pady=12):
    f = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    f.pack(fill="x", padx=14, pady=6)
    inner = tk.Frame(f, bg=CARD)
    inner.pack(fill="x", padx=padx, pady=pady)
    return inner


def mk_label(parent, text, size=10, fg=FG, bold=False, **kw):
    return tk.Label(parent, text=text, bg=kw.pop("bg", CARD), fg=fg,
                    font=(FONT, size, "bold" if bold else "normal"), **kw)


class Slider(tk.Canvas):
    """Deslizador propio (el tk.Scale nativo no se ve bien en tema oscuro).

    Escala logarítmica: se afina muy bien en la zona de 100-1500 cpm,
    que es la útil para likes.
    """

    MINV, MAXV = 1, 10000

    def __init__(self, parent, value=300, on_change=None, **kw):
        super().__init__(parent, height=34, bg=CARD, highlightthickness=0, bd=0, **kw)
        self.on_change = on_change
        self._value = int(value)
        self._pressing = False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_pressing", False))

    def _t_of(self, v):
        v = max(self.MINV, min(self.MAXV, v))
        return math.log(v) / math.log(self.MAXV + 1)

    def _v_of(self, t):
        t = max(0.0, min(1.0, t))
        return max(self.MINV, min(self.MAXV, int(round((self.MAXV + 1) ** t))))

    def set_value(self, v):
        self._value = max(self.MINV, min(self.MAXV, int(v)))
        self._redraw()

    def _press(self, ev):
        self._pressing = True
        self._move_to(ev.x)

    def _drag(self, ev):
        if self._pressing:
            self._move_to(ev.x)

    def _move_to(self, x):
        pad = 12
        w = max(1, self.winfo_width() - 2 * pad)
        v = self._v_of((x - pad) / w)
        if v != self._value:
            self._value = v
            self._redraw()
            if self.on_change:
                self.on_change(v)

    def _redraw(self):
        self.delete("all")
        w = max(40, self.winfo_width())
        cy = 17
        pad = 12
        x0, x1 = pad, w - pad
        self.create_line(x0, cy, x1, cy, fill=CARD2, width=8, capstyle="round")
        kx = x0 + (x1 - x0) * self._t_of(self._value)
        if kx > x0 + 1:
            self.create_line(x0, cy, kx, cy, fill=ACCENT, width=8, capstyle="round")
        for frac in (0.25, 0.5, 0.75):
            xm = x0 + (x1 - x0) * frac
            self.create_line(xm, cy - 12, xm, cy - 9, fill=LINE, width=2)
            self.create_line(xm, cy + 9, xm, cy + 12, fill=LINE, width=2)
        self.create_oval(kx - 9, cy - 9, kx + 9, cy + 9,
                         fill="#ffffff", outline=ACCENT, width=3)


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.events = queue.Queue()
        self.target = None
        self.clicker = None
        self.hotkey_vks = {}
        self._key_down = {}
        self._countdown = 0
        self._countdown_job = None
        self._started_at = None
        self._sync = False

        root.title(APP_TITLE)
        root.configure(bg=BG)

        self._build_ui()
        self._apply_config()

        self.root.update_idletasks()
        w = max(600, self.root.winfo_reqwidth())
        h = self.root.winfo_reqheight() + 12   # margen para que no se corte el pie
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(w, h)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(120, self._tick)
        root.after(25, self._poll_hotkeys)

    # ---------------------------------------------------------------- construcción UI
    def _build_ui(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 4))

        tk.Label(header, text="AutoClicker", bg=BG, fg=FG,
                 font=(FONT, 20, "bold")).pack(side="left")
        tk.Label(header, text="PRO", bg=BG, fg=ACCENT,
                 font=(FONT, 20, "bold")).pack(side="left", padx=(6, 0))
        self.lbl_status = tk.Label(header, text="● DETENIDO", bg=BG, fg=SUB,
                                   font=(FONT, 10, "bold"))
        self.lbl_status.pack(side="right", pady=(6, 0))

        tk.Label(self.root, text="Likes en TikTok sin bloquear el ratón ni el teclado",
                 bg=BG, fg=SUB, font=(FONT, 9)).pack(anchor="w", padx=21, pady=(0, 8))

        # ---- 1. Objetivo
        c1 = mk_card(self.root)
        mk_label(c1, "1 · Punto del botón", 10, CYAN, True).pack(anchor="w")

        row = tk.Frame(c1, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self.btn_mark = self._flat_button(row, "Marcar punto  (F2)", self.begin_mark,
                                          bg=CARD2, fg=FG, width=20)
        self.btn_mark.pack(side="left")
        self.lbl_point = mk_label(row, "Sin marcar", 9, SUB)
        self.lbl_point.pack(side="left", padx=10)

        self.lbl_window = mk_label(c1, "Ninguna ventana seleccionada", 9, SUB,
                                   anchor="w", justify="left")
        self.lbl_window.pack(fill="x", pady=(6, 0))

        mk_label(c1, "Pulsa F2 con el cursor encima del corazón de TikTok, o usa el "
                     "botón (3 s para colocarlo).", 8, SUB,
                 anchor="w", justify="left", wraplength=540).pack(fill="x", pady=(4, 0))

        # ---- 2. Velocidad
        c2 = mk_card(self.root)
        head = tk.Frame(c2, bg=CARD)
        head.pack(fill="x")
        mk_label(head, "2 · Clicks por minuto", 10, CYAN, True).pack(side="left")
        self.cpm_var = tk.IntVar(value=int(self.cfg["cpm"]))
        self.spin_cpm = tk.Spinbox(head, from_=1, to=10000, increment=10, width=7,
                                   bg=CARD2, fg=FG, buttonbackground=CARD2,
                                   insertbackground=FG, relief="flat", justify="center",
                                   font=(FONT, 11, "bold"), highlightthickness=0,
                                   textvariable=self.cpm_var, command=self._on_spin)
        self.spin_cpm.pack(side="right")
        self.spin_cpm.bind("<KeyRelease>", lambda e: self._on_spin())
        self.spin_cpm.bind("<FocusOut>", lambda e: self._on_spin(force=True))

        self.slider = Slider(c2, value=int(self.cfg["cpm"]), on_change=self.set_cpm)
        self.slider.pack(fill="x", pady=(8, 2))

        presets = tk.Frame(c2, bg=CARD)
        presets.pack(fill="x")
        for v in (60, 300, 600, 1200, 3000, 10000):
            self._flat_button(presets, f"{v}", lambda v=v: self.set_cpm(v),
                              bg=CARD2, fg=SUB, width=6, size=8).pack(side="left", padx=(0, 6))

        self.lbl_rate = mk_label(c2, "", 9, SUB, anchor="w")
        self.lbl_rate.pack(fill="x", pady=(6, 0))

        # ---- 3. Modo
        c3 = mk_card(self.root)
        mk_label(c3, "3 · Cómo se hace el click", 10, CYAN, True).pack(anchor="w")
        self.mode_var = tk.StringVar(value=self.cfg["mode"])
        opt = dict(bg=CARD, fg=FG, activebackground=CARD, activeforeground=FG,
                   selectcolor=CARD2, font=(FONT, 9), anchor="w",
                   highlightthickness=0, bd=0)
        self.rb_post = tk.Radiobutton(
            c3, text="Ventana (recomendado) — tu ratón sigue libre",
            variable=self.mode_var, value="post", command=self._on_mode, **opt)
        self.rb_post.pack(fill="x", pady=(6, 0))
        self.rb_phys = tk.Radiobutton(
            c3, text="Físico — mueve el cursor un instante (si el otro falla)",
            variable=self.mode_var, value="fisico", command=self._on_mode, **opt)
        self.rb_phys.pack(fill="x")
        self.restore_var = tk.BooleanVar(value=self.cfg["restore"])
        self.chk_restore = tk.Checkbutton(
            c3, text="Devolver el cursor a su sitio tras cada click",
            variable=self.restore_var, command=self._save_cfg, **{**opt, "font": (FONT, 8)})
        self.chk_restore.pack(fill="x", padx=(24, 0))

        # ---- 4. Pausa inteligente
        c4 = mk_card(self.root, pady=10)
        self.pause_var = tk.BooleanVar(value=self.cfg["pause_input"])
        self.chk_pause = tk.Checkbutton(
            c4, text="Pausar mientras uso el ratón o el teclado",
            variable=self.pause_var, command=self._save_cfg, **{**opt, "font": (FONT, 10)})
        self.chk_pause.pack(anchor="w")
        mk_label(c4, "Actívalo si prefieres que los clicks se detengan mientras usas el PC "
                     "y sigan solos ~0,7 s después. Desactivado, sigue dando likes aunque "
                     "estés en otra ventana (sin quitarte el foco).",
                 8, SUB, anchor="w", justify="left",
                 wraplength=540).pack(fill="x", padx=(24, 0))

        # ---- Acciones
        act = tk.Frame(self.root, bg=BG)
        act.pack(fill="x", padx=14, pady=(8, 0))
        self.btn_toggle = tk.Button(act, text="▶  INICIAR   (T)", command=self.toggle,
                                    bg=ACCENT, fg="white", relief="flat", bd=0,
                                    font=(FONT, 13, "bold"), activebackground="#d81f45",
                                    activeforeground="white", cursor="hand2", pady=12)
        self.btn_toggle.pack(side="left", fill="x", expand=True)
        self.btn_test = tk.Button(act, text="Probar\n5 clicks", command=self.test_clicks,
                                  bg=CARD2, fg=FG, relief="flat", bd=0,
                                  font=(FONT, 9), activebackground=LINE,
                                  activeforeground=FG, cursor="hand2", padx=12)
        self.btn_test.pack(side="left", padx=(8, 0))

        # ---- Stats
        stats = tk.Frame(self.root, bg=BG)
        stats.pack(fill="x", padx=14, pady=(10, 0))
        self.stat_clicks = self._stat(stats, "CLICKS", "0")
        self.stat_cpm = self._stat(stats, "VELOCIDAD REAL", "—")
        self.stat_time = self._stat(stats, "TIEMPO", "00:00")

        # ---- Pie
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=20, pady=(12, 14), side="bottom")
        self.lbl_keys = mk_label(foot, "", 8, SUB, bg=BG, anchor="w", justify="left",
                                 wraplength=560)
        self.lbl_keys.pack(fill="x")
        mk_label(foot, "Consejo: 300–600 cpm ya da likes seguidos; por encima de ~1500 "
                       "TikTok puede ignorar algunos.",
                 8, "#5f6b78", bg=BG, anchor="w", justify="left",
                 wraplength=560).pack(fill="x", pady=(4, 0))

    def _flat_button(self, parent, text, cmd, bg=CARD2, fg=FG, width=None, size=9):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, relief="flat",
                      bd=0, font=(FONT, size, "bold" if size >= 10 else "normal"),
                      activebackground=LINE, activeforeground=FG, cursor="hand2",
                      padx=10, pady=6)
        if width:
            b.configure(width=width)
        return b

    def _stat(self, parent, caption, value):
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(side="left", fill="x", expand=True, padx=3)
        tk.Label(box, text=caption, bg=CARD, fg=SUB, font=(FONT, 7, "bold")).pack(pady=(7, 0))
        lbl = tk.Label(box, text=value, bg=CARD, fg=FG, font=(FONT, 16, "bold"))
        lbl.pack(pady=(0, 7))
        return lbl

    # ---------------------------------------------------------------- config
    def _apply_config(self):
        c = self.cfg
        self.set_cpm(c["cpm"])
        self.mode_var.set(c["mode"] if c["mode"] in ("post", "fisico") else "post")
        self.restore_var.set(bool(c["restore"]))
        self.pause_var.set(bool(c["pause_input"]))
        self._on_mode(save=False)
        pt = c.get("point")
        if isinstance(pt, dict) and "sx" in pt and "sy" in pt:
            hwnd = user32.WindowFromPoint(wt.POINT(int(pt["sx"]), int(pt["sy"])))
            if hwnd:
                cand = Target(hwnd, pt["sx"], pt["sy"])
                saved_cls = pt.get("cls")
                if not saved_cls or cand.top_class != saved_cls:
                    self.lbl_point.configure(text="⚠ vuelve a marcar", fg=AMBER)
                    self.lbl_window.configure(
                        text="El punto guardado ya no cae sobre la misma ventana "
                             "(¿moviste o cerraste TikTok?). Pulsa F2 sobre el corazón.")
                else:
                    self.target = cand
                    self._show_target()
        self._refresh_keys_label()
        self._update_hotkeys()

    def _save_cfg(self):
        if self._sync:
            return
        try:
            cpm = int(self.cpm_var.get())
        except Exception:
            cpm = self.cfg["cpm"]
        self.cfg.update({
            "cpm": max(1, min(10000, cpm)),
            "mode": self.mode_var.get(),
            "restore": bool(self.restore_var.get()),
            "pause_input": bool(self.pause_var.get()),
        })
        if self.target:
            self.cfg["point"] = self.target.as_dict()
        save_config(self.cfg)

    def _on_mode(self, save=True):
        phys = self.mode_var.get() == "fisico"
        self.chk_restore.configure(state="normal" if phys else "disabled",
                                   fg=FG if phys else "#5f6b78")
        # la pausa por actividad sólo tiene sentido con clicks "invisibles"
        self.chk_pause.configure(state="disabled" if phys else "normal",
                                 fg="#5f6b78" if phys else FG)
        if phys and self.pause_var.get():
            self.pause_var.set(False)
        if save:
            self._save_cfg()

    def _refresh_keys_label(self):
        hk = "activados" if self.cfg.get("hotkeys", True) else "desactivados"
        self.lbl_keys.configure(
            text=f"Atajos {hk}:  {self.cfg['start_key']} = iniciar/detener    "
                 f"{self.cfg['stop_key']} = detener    {self.cfg['mark_key']} = marcar.  "
                 f"Se leen sin bloquear el teclado; con Ctrl/Alt/Mayús pulsado se ignoran.")

    def _update_hotkeys(self):
        self.hotkey_vks = {
            "start": key_to_vk(self.cfg["start_key"]),
            "stop": key_to_vk(self.cfg["stop_key"]),
            "mark": key_to_vk(self.cfg["mark_key"]),
        }
        self._key_down = {}

    # ---------------------------------------------------------------- velocidad
    def set_cpm(self, value):
        v = max(1, min(10000, int(value)))
        self._sync = True
        try:
            self.cpm_var.set(v)
            self.slider.set_value(v)
        finally:
            self._sync = False
        self._update_derived()

    def _on_spin(self, force=False):
        if self._sync:
            return
        try:
            v = int(self.cpm_var.get())
        except Exception:
            if force:
                self.set_cpm(self.cfg.get("cpm", 300))
            return
        self.set_cpm(v)

    def _update_derived(self):
        try:
            v = max(1, min(10000, int(self.cpm_var.get())))
        except Exception:
            return
        interval = 60000.0 / v
        self.lbl_rate.configure(
            text=f"= 1 click cada {interval:.0f} ms  ·  {v / 60.0:.1f} clicks por segundo")

    # ---------------------------------------------------------------- marcar punto
    def begin_mark(self):
        if self._countdown:
            return
        self._countdown = 3
        self._tick_countdown()

    def _tick_countdown(self):
        if self._countdown <= 0:
            self._countdown_job = None
            self.btn_mark.configure(text="Marcar punto  (F2)")
            self.capture_point()
            return
        self.btn_mark.configure(text=f"Capturando en {self._countdown}…")
        self._countdown -= 1
        self._countdown_job = self.root.after(1000, self._tick_countdown)

    def capture_point(self):
        sx, sy = cursor_pos()
        hwnd = user32.WindowFromPoint(wt.POINT(sx, sy))
        if not hwnd:
            messagebox.showwarning(APP_TITLE, "No hay ninguna ventana en ese punto.")
            return
        try:
            own = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        except Exception:
            own = None
        if own and toplevel(hwnd) == own:
            messagebox.showwarning(APP_TITLE,
                                   "Has marcado sobre esta misma ventana.\n"
                                   "Coloca el cursor sobre el botón de TikTok.")
            return
        self.target = Target(hwnd, sx, sy)
        self._show_target()
        self._save_cfg()

    def _show_target(self):
        t = self.target
        if not t:
            self.lbl_point.configure(text="Sin marcar", fg=SUB)
            self.lbl_window.configure(text="Ninguna ventana seleccionada")
            return
        self.lbl_point.configure(text=f"X {t.sx} · Y {t.sy}", fg=GREEN)
        self.lbl_window.configure(text=f"Ventana: {t.title[:70]}", fg=SUB)

    # ---------------------------------------------------------------- atajos (sondeo)
    def _poll_hotkeys(self):
        try:
            if self.cfg.get("hotkeys", True):
                held = {name: bool(user32.GetAsyncKeyState(vk) & 0x8000)
                        for name, vk in self.hotkey_vks.items() if vk}
                mods = any(user32.GetAsyncKeyState(m) & 0x8000 for m in MODIFIER_VKS)
                for name, vk in self.hotkey_vks.items():
                    if not vk:
                        continue
                    if held.get(name):
                        if not self._key_down.get(vk):
                            self._key_down[vk] = True
                            if not mods:
                                self._on_hotkey(name)
                    else:
                        self._key_down[vk] = False
        except Exception:
            pass
        self.root.after(25, self._poll_hotkeys)

    def _on_hotkey(self, name):
        if name == "start":
            self.toggle()
        elif name == "stop":
            self.stop()
        elif name == "mark":
            if not self._countdown:
                self.capture_point()

    # ---------------------------------------------------------------- motor
    def toggle(self):
        if self.clicker:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.clicker:
            return
        if not self.target:
            messagebox.showwarning(APP_TITLE, "Primero marca el punto del botón (F2).")
            return
        if not self.target.revalidate():
            messagebox.showwarning(APP_TITLE, "La ventana marcada ya no existe. Vuelve a marcarla.")
            return
        self._show_target()
        try:
            cpm = int(self.cpm_var.get())
        except Exception:
            cpm = self.cfg["cpm"]
        mode = self.mode_var.get()
        pause = bool(self.pause_var.get()) and mode == "post"
        self.clicker = Clicker(self.target, cpm, mode,
                               bool(self.restore_var.get()), self.events, pause)
        self.clicker.start()
        self._started_at = time.perf_counter()
        self.stat_clicks.configure(text="0")
        self.stat_cpm.configure(text="—")
        self.stat_time.configure(text="00:00")
        self.btn_toggle.configure(text="■  DETENER   (X)", bg="#3a4550",
                                  activebackground="#4a5764")
        self.lbl_status.configure(text="● ACTIVO", fg=GREEN)
        self._save_cfg()

    def stop(self, message=None):
        if self.clicker:
            self.clicker.stop()
            self.clicker = None
        self.btn_toggle.configure(text="▶  INICIAR   (T)", bg=ACCENT,
                                  activebackground="#d81f45")
        self.lbl_status.configure(text="● DETENIDO", fg=SUB)
        self._started_at = None
        if message:
            messagebox.showwarning(APP_TITLE, message)

    def test_clicks(self):
        if self.clicker:
            return
        if not self.target or not self.target.revalidate():
            messagebox.showwarning(APP_TITLE, "Primero marca el punto del botón (F2).")
            return
        mode, restore = self.mode_var.get(), bool(self.restore_var.get())
        target = self.target

        def run():
            for _ in range(5):
                try:
                    if mode == "post":
                        post_click(target.hwnd, target.cx, target.cy)
                    else:
                        physical_click(target.sx, target.sy, restore)
                except Exception:
                    pass
                time.sleep(0.12)
            self.events.put(("msg", "Prueba enviada: 5 clicks."))

        threading.Thread(target=run, daemon=True).start()

    # ---------------------------------------------------------------- bucle UI
    def _tick(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "lost":
                    self.stop(payload)
                elif kind == "msg":
                    self.lbl_rate.configure(text=payload, fg=CYAN)
                    self.root.after(2500, self._update_derived)
        except queue.Empty:
            pass

        if self.clicker:
            if self.clicker.paused:
                self.lbl_status.configure(text="● PAUSA (usas el PC)", fg=AMBER)
            elif self.lbl_status.cget("text") != "● ACTIVO":
                self.lbl_status.configure(text="● ACTIVO", fg=GREEN)
            if self._started_at:
                clicks = self.clicker.clicks
                elapsed = max(0.001, time.perf_counter() - self._started_at)
                self.stat_clicks.configure(text=f"{clicks:,}".replace(",", "."))
                self.stat_cpm.configure(text=f"{clicks / elapsed * 60:,.0f}".replace(",", "."))
                m, s = divmod(int(elapsed), 60)
                self.stat_time.configure(text=f"{m:02d}:{s:02d}")

        self.root.after(120, self._tick)

    # ---------------------------------------------------------------- cerrar
    def on_close(self):
        self._save_cfg()
        if self.clicker:
            self.clicker.stop()
        if self._countdown_job:
            self.root.after_cancel(self._countdown_job)
        self.root.after(120, self.root.destroy)


# --------------------------------------------------------------------------------------
# Modo diagnóstico y banco de pruebas (sin interfaz)
# --------------------------------------------------------------------------------------
def diag(do_click=False):
    set_dpi_aware()
    x, y = cursor_pos()
    hwnd = user32.WindowFromPoint(wt.POINT(x, y))
    print(f"cursor = ({x}, {y})")
    if hwnd:
        t = Target(hwnd, x, y)
        print(f"hwnd   = {hwnd}")
        print(f"titulo = {t.title}")
        print(f"clase  = {window_class(t.hwnd)}")
        print(f"cliente= ({t.cx}, {t.cy})")
        if do_click:
            print("post_click ->", post_click(t.hwnd, t.cx, t.cy))
    else:
        print("sin ventana bajo el cursor")
    for key in ("T", "X", "F2"):
        vk = key_to_vk(key)
        print(f"vk({key}) = {hex(vk) if vk else 'None'}")


def bench():
    cpm = 6000
    interval = 60.0 / cpm
    n = 0
    start = time.perf_counter()
    nxt = start
    end = start + 2.0
    while time.perf_counter() < end:
        n += 1
        nxt += interval
        now = time.perf_counter()
        if nxt < now:
            nxt = now
        remain = nxt - now
        if remain > 0.0005:
            time.sleep(remain)
    dt = time.perf_counter() - start
    print(f"{n} iteraciones en {dt:.3f}s = {n / dt * 60:,.0f} cpm (objetivo {cpm})")
    print(f"inactividad detectada: {idle_ms()} ms")


def main():
    if "--diag" in sys.argv:
        diag("--click" in sys.argv)
        return
    if "--bench" in sys.argv:
        bench()
        return
    set_dpi_aware()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

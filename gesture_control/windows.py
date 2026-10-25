# SPDX-License-Identifier: GPL-3.0-only
"""Small Win32 adapter. Imported only on Windows; no admin access required."""
import ctypes
from ctypes import wintypes


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class Payload(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("payload", Payload)]


class Windows:
    def __init__(self, control=False):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.api.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self.api.SendInput.restype = wintypes.UINT
        self.api.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        self.api.SetCursorPos.restype = wintypes.BOOL
        self.api.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self.api.GetAsyncKeyState.restype = wintypes.SHORT
        self.api.GetSystemMetrics.argtypes = (ctypes.c_int,)
        self.api.GetSystemMetrics.restype = ctypes.c_int
        try:
            self.api.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except AttributeError:
            self.api.SetProcessDPIAware()
        self.width = self.api.GetSystemMetrics(0)
        self.height = self.api.GetSystemMetrics(1)
        self.control = control
        self.down = False
        self.right_down = False
        self.keys = {}

    def pressed(self, key):
        held = bool(self.api.GetAsyncKeyState(key) & 0x8000)
        previous = self.keys.get(key, False)
        self.keys[key] = held
        return held and not previous

    def _mouse(self, flag, data=0):
        event = INPUT(type=0, payload=Payload(mi=MOUSEINPUT(0, 0, data & 0xffffffff, flag, 0, 0)))
        if self.api.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise RuntimeError("Windows rejected mouse input. Elevated applications may block input.")

    def apply(self, actions):
        if not self.control:
            return
        for action in actions:
            if action.kind == "move":
                if not self.api.SetCursorPos(round(action.x * (self.width - 1)), round(action.y * (self.height - 1))):
                    raise RuntimeError("Windows rejected cursor movement")
            elif action.kind == "down":
                self._mouse(0x0002)
                self.down = True
            elif action.kind == "up":
                self._mouse(0x0004)
                self.down = False
            elif action.kind == "click":
                self._mouse(0x0002)
                self.down = True
                self._mouse(0x0004)
                self.down = False
            elif action.kind == "right_click":
                self._mouse(0x0008)
                self.right_down = True
                self._mouse(0x0010)
                self.right_down = False
            elif action.kind == "scroll":
                self._mouse(0x0800, round(action.x) * 120)

    def close(self):
        if self.control:
            try:
                if self.down:
                    self._mouse(0x0004)
                    self.down = False
            finally:
                if self.right_down:
                    self._mouse(0x0010)
                    self.right_down = False

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import sys
import time
from pathlib import Path


def write_result(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    result_path = Path(sys.argv[1])
    result: dict[str, object] = {
        "started": True,
        "window_found": False,
        "button_found": False,
        "clicked": False,
        "error": "",
    }
    write_result(result_path, result)
    time.sleep(1.0)

    try:
        user32 = ctypes.windll.user32
        bm_click = 0x00F5
        title = "EnergoLogic — инструменты Visio"
        button_text = "Копировать →"

        def window_text(hwnd: int) -> str:
            length = int(user32.GetWindowTextLengthW(hwnd))
            buf = ctypes.create_unicode_buffer(max(1, length + 1))
            user32.GetWindowTextW(hwnd, buf, len(buf))
            return buf.value

        proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        windows: list[int] = []

        @proc
        def enum_window(hwnd, _lparam):
            if bool(user32.IsWindowVisible(hwnd)) and window_text(hwnd) == title:
                windows.append(int(hwnd))
            return True

        user32.EnumWindows(enum_window, 0)
        if not windows:
            raise RuntimeError("EnergoLogic editor window not found")
        result["window_found"] = True
        root = windows[-1]
        result["window_hwnd"] = root
        write_result(result_path, result)

        buttons: list[int] = []

        @proc
        def enum_child(hwnd, _lparam):
            if window_text(hwnd) == button_text:
                buttons.append(int(hwnd))
            return True

        user32.EnumChildWindows(root, enum_child, 0)
        if not buttons:
            raise RuntimeError("EnergoLogic Duplicate Right button not found")
        result["button_found"] = True
        button = buttons[-1]
        result["button_hwnd"] = button
        write_result(result_path, result)

        rect = ctypes.wintypes.RECT()
        if not bool(user32.GetWindowRect(button, ctypes.byref(rect))):
            raise RuntimeError("Could not read EnergoLogic button bounds")
        x = int((rect.left + rect.right) // 2)
        y = int((rect.top + rect.bottom) // 2)
        result["button_bounds"] = {
            "left": int(rect.left), "top": int(rect.top),
            "right": int(rect.right), "bottom": int(rect.bottom),
            "x": x, "y": y,
        }
        old_cursor = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(old_cursor))
        user32.ShowWindow(root, 9)
        user32.BringWindowToTop(root)
        user32.SetForegroundWindow(root)
        time.sleep(0.2)
        user32.SetCursorPos(x, y)
        time.sleep(0.1)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        result["clicked"] = True
        time.sleep(0.5)
        user32.SetCursorPos(int(old_cursor.x), int(old_cursor.y))
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        write_result(result_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

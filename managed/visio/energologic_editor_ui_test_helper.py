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

        user32.SendMessageW(button, bm_click, 0, 0)
        result["clicked"] = True
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        write_result(result_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

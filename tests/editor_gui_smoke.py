from __future__ import annotations

import importlib.util
from pathlib import Path
import time
import tkinter as tk


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = next(ROOT.glob("*SanWich.py"))
SPEC = importlib.util.spec_from_file_location("sanwich_app_smoke", APP_PATH)
APP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(APP)


def descendants(widget):
    result = []
    for child in widget.winfo_children():
        result.append(child)
        result.extend(descendants(child))
    return result


def widget_text(widget):
    try:
        return str(widget.cget("text"))
    except Exception:
        return ""


def visible_caption_texts(editor):
    items = [w for w in descendants(editor) if isinstance(w, tk.Text) and w.winfo_manager()]
    return sorted(items, key=lambda w: (int(w.grid_info().get("row", 0)), w.winfo_y()))


def visible_number_buttons(editor):
    items = [
        w for w in descendants(editor)
        if isinstance(w, tk.Button) and widget_text(w).isdigit() and w.winfo_manager()
    ]
    return sorted(items, key=lambda w: int(w.grid_info().get("row", 0)))


def main():
    srt_path = next(Path.home().joinpath("Downloads").glob("EP143*修改.srt"))
    media_path = next(Path.home().joinpath("Downloads").glob("EP143*.mkv"))
    chunks = APP.parse_srt_text(srt_path.read_text(encoding="utf-8-sig"))
    assert len(chunks) == 2069

    # 在第 304 組放入可預期的 200 ms 衝突，驗證檢查後會切到含該行的第 2 頁。
    previous_end = chunks[302]["timestamp"][1]
    start, end = chunks[303]["timestamp"]
    chunks[303]["timestamp"] = (min(start, previous_end - 0.2), end)

    APP.build_waveform_proxy = lambda *_args, **_kwargs: ([0.2] * 600, chunks[-1]["timestamp"][1], None)
    APP.App.check_for_updates_async = lambda _self: None
    errors = []
    APP.messagebox.showerror = lambda title, message: errors.append((title, message))
    APP.messagebox.showinfo = lambda *_args, **_kwargs: None
    APP.messagebox.showwarning = lambda *_args, **_kwargs: None

    app = APP.App()
    app.withdraw()
    app.last_result = {
        "inp": str(media_path),
        "srt": "",
        "txt": "",
        "chunks": APP.clone_chunks(chunks),
    }

    opened_at = time.perf_counter()
    app.open_srt_editor()
    app.update()
    editor = next(w for w in app.winfo_children() if isinstance(w, APP.ctk.CTkToplevel))
    open_seconds = time.perf_counter() - opened_at

    texts = visible_caption_texts(editor)
    entries = [w for w in descendants(editor) if isinstance(w, tk.Entry) and w.winfo_manager()]
    numbers = visible_number_buttons(editor)
    assert len(texts) == 160, len(texts)
    assert len(entries) == 320, len(entries)
    assert widget_text(numbers[0]) == "1"
    assert widget_text(numbers[-1]) == "160"

    original = texts[0].get("1.0", "end").strip()
    texts[0].event_generate("<FocusIn>")
    app.update()
    texts[0].delete("1.0", "end")
    texts[0].insert("1.0", "Redo效能測試")
    undo = next(w for w in descendants(editor) if widget_text(w) == "↶")
    redo = next(w for w in descendants(editor) if widget_text(w) == "↷")

    undo_started = time.perf_counter()
    undo.invoke()
    app.update()
    undo_seconds = time.perf_counter() - undo_started
    assert visible_caption_texts(editor)[0].get("1.0", "end").strip() == original

    redo_started = time.perf_counter()
    redo.invoke()
    app.update()
    redo_seconds = time.perf_counter() - redo_started
    assert visible_caption_texts(editor)[0].get("1.0", "end").strip() == "Redo效能測試"

    check = next(w for w in descendants(editor) if widget_text(w) == "檢查時間軸")
    check.invoke()
    app.update()
    numbers = visible_number_buttons(editor)
    assert errors and "第 304 組" in errors[-1][1], errors
    assert widget_text(numbers[0]) == "161"
    assert widget_text(numbers[-1]) == "320"

    print(
        f"PASS rows={len(chunks)} rendered_texts={len(texts)} rendered_entries={len(entries)} "
        f"open={open_seconds:.3f}s undo={undo_seconds:.3f}s redo={redo_seconds:.3f}s "
        f"jump={errors[-1][1]}"
    )
    editor.destroy()
    app.destroy()


if __name__ == "__main__":
    main()

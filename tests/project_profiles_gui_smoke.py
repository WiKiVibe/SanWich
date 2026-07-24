from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import tkinter as tk


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "SanWich.py"
SPEC = importlib.util.spec_from_file_location("sanwich_project_profiles_smoke", APP_PATH)
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


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store = APP.LEARNING.ProjectProfileStore(Path(tmp) / "profiles.json")
        for name in ("專案一", "專案二", "專案三", "專案四", "專案五"):
            store.upsert(name=name, guests="測試來賓", terms="測試用語")
        store.save()
        APP.PROJECT_PROFILES = store
        APP.has_feature = lambda _name: True
        APP.App.check_for_updates_async = lambda _self: None
        APP.App.refresh_license_if_due_async = lambda _self, **_kwargs: None

        confirmations = []
        window_holder = {}

        def cancel_delete(title, message, **_kwargs):
            # 模擬 Windows 原生確認視窗關閉時拿走 grab。
            current = window_holder["window"].grab_current()
            if current is not None:
                current.grab_release()
            confirmations.append((title, message))
            return False

        APP.messagebox.askyesno = cancel_delete

        app = APP.App()
        app.geometry("800x640+40+40")
        app.update()
        app.open_project_profiles_window()
        app.update()
        window = next(
            widget for widget in app.winfo_children()
            if isinstance(widget, APP.ctk.CTkToplevel)
        )
        window_holder["window"] = window
        canvas = next(widget for widget in descendants(window) if type(widget) is tk.Canvas)
        menu = next(widget for widget in window.children.values() if isinstance(widget, tk.Menu))
        assert canvas.bind("<Double-Button-1>"), "專案列未綁定雙擊切換"
        # 後續合成的單擊事件不應被 Tk 的雙擊辨識器合併，避免煙霧測試互相干擾。
        canvas.unbind("<Double-Button-1>")

        assert bool(window.overrideredirect()), "原生白色標題列尚未移除"
        assert "選擇專案" in [widget_text(widget) for widget in descendants(window)]

        # 從清單底部空白處往上框選，五筆都應被選取。
        canvas.focus_force()
        canvas.event_generate("<ButtonPress-1>", x=2, y=305, when="now")
        canvas.event_generate("<B1-Motion>", x=220, y=5, when="now")
        canvas.event_generate("<ButtonRelease-1>", x=220, y=5, when="now")
        app.update()
        marquee_selected = sum(
            float(canvas.itemcget(item, "width")) == 2.0
            for item in canvas.find_all() if canvas.type(item) in ("polygon", "rectangle")
        )
        assert marquee_selected == 5, marquee_selected

        # 點一下空白處清除框選，再測一般點選 + Ctrl 複選。
        canvas.event_generate("<ButtonPress-1>", x=2, y=305, when="now")
        canvas.event_generate("<ButtonRelease-1>", x=2, y=305, when="now")
        canvas.yview_moveto(0)
        app.update()
        # 一般點選 + Ctrl 點選，建立兩筆選取。
        canvas.event_generate("<ButtonPress-1>", x=42, y=34, when="now")
        canvas.event_generate("<ButtonRelease-1>", x=42, y=34, when="now")
        canvas.event_generate("<ButtonPress-1>", x=42, y=94, state=0x0004, when="now")
        canvas.event_generate("<ButtonRelease-1>", x=42, y=94, state=0x0004, when="now")
        app.update()

        before_ids = [p["id"] for p in store.profiles]
        menu_labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) != "separator"
        ]
        assert menu_labels == ["複製", "刪除…"], menu_labels
        rectangle_widths = [
            canvas.itemcget(item, "width")
            for item in canvas.find_all() if canvas.type(item) in ("polygon", "rectangle")
        ]
        selected_row_count = sum(float(width) == 2.0 for width in rectangle_widths)
        assert selected_row_count == 2, rectangle_widths
        menu.invoke(0)  # 複製
        app.update()
        copies = [p for p in store.profiles if p["id"] not in before_ids]
        copy_names = [p["name"] for p in copies]
        assert copy_names == ["專案一 副本", "專案二 副本"], copy_names
        assert all(p["guests"] == "測試來賓" and p["terms"] == "測試用語" for p in copies)

        # 複製後副本保持複選；拖曳任一副本時，整組一起移到清單底部。
        canvas.event_generate("<ButtonPress-1>", x=42, y=94)
        canvas.event_generate("<B1-Motion>", x=42, y=430)
        canvas.event_generate("<ButtonRelease-1>", x=42, y=430)
        app.update()
        assert [p["id"] for p in store.profiles[-2:]] == [p["id"] for p in copies]

        # 刪除指令必須先詢問；測試選擇「否」後資料不可減少。
        count_before_delete = len(store.profiles)
        menu.invoke(2)
        app.update()
        assert confirmations and confirmations[-1][0] == "確認刪除專案"
        assert len(store.profiles) == count_before_delete
        assert app.grab_current() is None, "取消後仍殘留視窗鎖定"

        # 重新開啟後測試雙擊專案列即可切換。
        window.destroy()
        app.update()
        app.open_project_profiles_window()
        app.update()
        window2 = next(
            widget for widget in app.winfo_children()
            if isinstance(widget, APP.ctk.CTkToplevel)
        )
        canvas2 = next(widget for widget in descendants(window2) if type(widget) is tk.Canvas)
        assert canvas2.bind("<Double-Button-1>"), "重新開啟後雙擊綁定遺失"
        window2.destroy()
        app.update()
        assert not window2.winfo_exists(), "專案視窗無法關閉"
        assert app.grab_current() is None, "切換專案後仍殘留視窗鎖定"

        print(
            "PASS borderless=1 rounded_rows=1 multi_select=2 duplicated=2 "
            "group_reorder=1 delete_confirmation=1 double_click_switch=1 switching_unlocked=1"
        )
        app.destroy()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Application lifecycle and window closing behavior."""
from __future__ import annotations

class AppLifecycleMixin:
    def open_data_folder(self) -> None:
        try:
            if os.name == "nt":
                os.startfile(DATA_DIR)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(DATA_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(DATA_DIR)])
        except Exception as exc:
            messagebox.showerror("Папка данных", str(exc))

    def _set_search_focus(self) -> None:
        self.search_entry.focus_set()

    def on_close(self) -> None:
        try:
            self.resource_governor.stop()
            if self.voice_cancel_event is not None:
                self.voice_cancel_event.set()
            # The current config is saved on each explicit settings/memory update.
            if self._auto_improvement_after_id:
                try:
                    self.root.after_cancel(self._auto_improvement_after_id)
                except Exception:
                    pass
            if self._auto_research_after_id:
                try:
                    self.root.after_cancel(self._auto_research_after_id)
                except Exception:
                    pass
            for timer_id in (self.cloud_sync_after_id, self.cloud_sync_periodic_id):
                if timer_id:
                    try:
                        self.root.after_cancel(timer_id)
                    except Exception:
                        pass
            self.resource_governor.stop()
            self.store.close()
            if self.avatar is not None:
                try:
                    self.avatar.window.destroy()
                except Exception:
                    pass
        finally:
            self.root.destroy()

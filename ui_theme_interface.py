# -*- coding: utf-8 -*-
"""Theme, palette, widget styling and Windows window integration."""
from __future__ import annotations

class UIThemeMixin:
    def _make_checkbox(self, master: tk.Misc, text: str, variable: tk.BooleanVar,
                       command=None, *, background_key: str = "panel", wraplength: int = 860) -> PurpleCheckbox:
        palette = self.colors
        control = PurpleCheckbox(
            master, text, variable, command, font=(self.font_family, 10), wraplength=wraplength,
            background=palette.get(background_key, palette["panel"]), foreground=palette["text"],
            accent=palette["check_accent"], border=palette["check_border"],
        )
        self.purple_checkboxes.append((control, background_key))
        return control

    @staticmethod
    def _palette_for_name(theme_name: str) -> dict[str, str]:
        if theme_name != "Светлая":
            return {
                "bg": "#0B1220", "sidebar": "#0A1020", "surface": "#111C2F",
                "panel": "#17243A", "panel2": "#1B2B45", "input": "#0D1729",
                "text": "#ECF2FC", "muted": "#91A3BE", "accent": "#8B76C5",
                "accent_hover": "#7660B1", "select": "#302644", "border": "#26364E",
                "user_bubble": "#243B62", "assistant_bubble": "#18283F",
                "success": "#56D6A0", "danger": "#FF8585", "hint": "#8795AD",
                "recent_card": "#111A2B", "recent_hover": "#1B2940",
                "recent_selected": "#29213D", "recent_border": "#26364E",
                "recent_selected_border": "#8068B6", "check_accent": "#4B356F",
                "check_border": "#8A79A5",
            }
        return {
            "bg": "#F3F5FA", "sidebar": "#E9EDF5", "surface": "#FFFFFF",
            "panel": "#FFFFFF", "panel2": "#F7F8FC", "input": "#FAFBFE",
            "text": "#20243A", "muted": "#68718A", "accent": "#66508F",
            "accent_hover": "#554078", "select": "#E9E2F4", "border": "#DCE1EB",
            "user_bubble": "#E4ECFF", "assistant_bubble": "#F4F7FC",
            "success": "#168568", "danger": "#C24141", "hint": "#75849A",
            "recent_card": "#FFFFFF", "recent_hover": "#F4F0FA",
            "recent_selected": "#EDE7F6", "recent_border": "#DCE1EB",
            "recent_selected_border": "#8068B6", "check_accent": "#514078",
            "check_border": "#87779D",
        }

    def _palette_for_theme(self) -> dict[str, str]:
        return self._palette_for_name(str(self.config.get("theme", "Тёмная")))

    def _build_styles(self) -> None:
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("TButton", padding=(12, 9), font=(self.font_family, 10), relief="flat", borderwidth=0)
        self.style.configure("Accent.TButton", padding=(16, 11), font=(self.font_family, 10, "bold"), foreground="#ffffff", background="#5B83F6", borderwidth=0, relief="flat")
        self.style.map("Accent.TButton", background=[("active", "#4C73E8"), ("disabled", "#4B5872")])
        self.style.configure("Ghost.TButton", padding=(12, 9), font=(self.font_family, 9), borderwidth=0, relief="flat")
        self.style.configure("Nav.TButton", padding=(13, 11), anchor="w", font=(self.font_family, 11), borderwidth=0, relief="flat")
        self.style.configure("TNotebook", borderwidth=0)
        self.style.configure("TCombobox", padding=(8, 7), font=(self.font_family, 10))
        self.style.configure("TEntry", padding=(10, 9), font=(self.font_family, 10))
        self.style.configure("TScrollbar", gripcount=0, borderwidth=0, arrowsize=10, width=10)
        self.style.configure("TLabelframe", padding=14, borderwidth=1, relief="solid")
        self.style.configure("TLabelframe.Label", font=(self.font_family, 11, "bold"))
        self.style.configure("TCheckbutton", padding=(2, 5), font=(self.font_family, 10))
        self.style.configure("TRadiobutton", padding=(2, 5), font=(self.font_family, 9))
        self.style.configure("TSeparator", relief="flat")

    def _apply_theme(self) -> None:
        colors = self._palette_for_theme()
        self.colors = colors
        self.root.configure(bg=colors["bg"])
        self.root.after_idle(self._apply_windows_titlebar_theme)
        self.shell.configure(style="Main.TFrame")
        self.sidebar.configure(style="Sidebar.TFrame")
        self.main_area.configure(style="Main.TFrame")
        self.style.configure("TFrame", background=colors["bg"])
        self.style.configure("Main.TFrame", background=colors["bg"])
        self.style.configure("Sidebar.TFrame", background=colors["sidebar"])
        self.style.configure("ChatSurface.TFrame", background=colors["surface"])
        self.style.configure("Panel.TFrame", background=colors["panel"])
        self.style.configure("Composer.TFrame", background=colors["panel"], relief="flat", borderwidth=0)
        self.style.configure("TLabelframe", background=colors["panel"], foreground=colors["text"], bordercolor=colors["border"], lightcolor=colors["border"], darkcolor=colors["border"])
        self.style.configure("TLabelframe.Label", background=colors["panel"], foreground=colors["text"])
        self.style.configure("TLabel", background=colors["bg"], foreground=colors["text"], font=(self.font_family, 11))
        self.style.configure("Muted.TLabel", background=colors["bg"], foreground=colors["muted"], font=(self.font_family, 10))
        self.style.configure("MutedPanel.TLabel", background=colors["panel"], foreground=colors["muted"], font=(self.font_family, 10))
        self.style.configure("Hint.TLabel", background=colors["panel"], foreground=colors["hint"], font=(self.font_family, 9))
        self.style.configure("Panel.TLabel", background=colors["panel"], foreground=colors["text"])
        self.style.configure("Brand.TLabel", background=colors["sidebar"], foreground=colors["text"], font=(self.font_family, 15, "bold"))
        self.style.configure("BrandSub.TLabel", background=colors["sidebar"], foreground=colors["muted"], font=(self.font_family, 8, "bold"))
        self.style.configure("SidebarFooter.TLabel", background=colors["sidebar"], foreground=colors["muted"], font=(self.font_family, 9))
        self.style.configure("PageTitle.TLabel", background=colors["bg"], foreground=colors["text"], font=(self.font_family, 23, "bold"))
        self.style.configure("Section.TLabel", background=colors["sidebar"], foreground=colors["muted"], font=(self.font_family, 9, "bold"))
        self.style.configure("TEntry", fieldbackground=colors["input"], foreground=colors["text"], insertcolor=colors["text"], borderwidth=1, relief="flat", bordercolor=colors["border"], lightcolor=colors["border"], darkcolor=colors["border"])
        self.style.map("TEntry", bordercolor=[("focus", colors["accent"])])
        self.style.configure("TScrollbar", background=colors["panel"], troughcolor=colors["bg"], arrowcolor=colors["muted"], bordercolor=colors["bg"], lightcolor=colors["panel"], darkcolor=colors["panel"])
        self.style.map("TScrollbar", background=[("active", colors["accent"])])
        self.style.configure("TCombobox", fieldbackground=colors["input"], background=colors["panel"], foreground=colors["text"], arrowcolor=colors["muted"], borderwidth=1, relief="flat", lightcolor=colors["border"], darkcolor=colors["border"], bordercolor=colors["border"])
        self.style.map("TCombobox", fieldbackground=[("readonly", colors["input"])], foreground=[("readonly", colors["text"])], selectbackground=[("readonly", colors["input"])], selectforeground=[("readonly", colors["text"])])
        self.style.configure("TButton", background=colors["panel2"], foreground=colors["text"], borderwidth=0, focuscolor=colors["panel2"], relief="flat", padding=(12, 9))
        self.style.map("TButton", background=[("active", colors["select"]), ("disabled", colors["panel2"])], foreground=[("disabled", colors["muted"])])
        self.style.configure("Ghost.TButton", background=colors["panel2"], foreground=colors["text"], borderwidth=0, focuscolor=colors["panel2"], relief="flat", padding=(12, 9))
        self.style.map("Ghost.TButton", background=[("active", colors["select"])])
        self.style.configure("Accent.TButton", background=colors["accent"], foreground="#FFFFFF", borderwidth=0, focuscolor=colors["accent"], relief="flat", padding=(16, 11), font=(self.font_family, 10, "bold"))
        self.style.map("Accent.TButton", background=[("active", colors["accent_hover"]), ("disabled", colors["muted"])], foreground=[("disabled", "#FFFFFF")])
        self.style.configure("Nav.TButton", background=colors["sidebar"], foreground=colors["muted"], borderwidth=0, focuscolor=colors["sidebar"], relief="flat", padding=(13, 11))
        self.style.map("Nav.TButton", background=[("pressed", colors["select"]), ("active", colors["panel2"])], foreground=[("pressed", colors["text"]), ("active", colors["text"])])
        self.style.configure("TCheckbutton", background=colors["panel"], foreground=colors["text"])
        self.style.configure("TRadiobutton", background=colors["panel"], foreground=colors["text"])
        self.style.configure("TScale", background=colors["panel"], troughcolor=colors["input"], sliderthickness=16)
        self.style.configure("Sidebar.TSeparator", background=colors["border"])

        text_widgets = [getattr(self, "chat_view", None), getattr(self, "input_box", None), getattr(self, "instructions_box", None), getattr(self, "improve_prompt_box", None), getattr(self, "patch_preview", None), getattr(self, "research_topics_box", None), getattr(self, "research_preview", None)]
        for widget in text_widgets:
            if widget:
                is_chat = widget is getattr(self, "chat_view", None)
                is_composer = widget is getattr(self, "input_box", None)
                bg = colors["surface"] if is_chat else (colors["input"] if is_composer else colors["panel2"])
                widget.configure(bg=bg, fg=colors["text"], insertbackground=colors["text"], selectbackground=colors["select"], selectforeground=colors["text"], highlightbackground=colors["border"], highlightcolor=colors["accent"])
        for name in ("memory_list", "skill_list", "research_list"):
            widget = getattr(self, name, None)
            if widget:
                widget.configure(bg=colors["panel2"], fg=colors["text"], selectbackground=colors["select"], selectforeground=colors["text"], highlightbackground=colors["border"], highlightcolor=colors["accent"], borderwidth=0)
        if hasattr(self, "chat_list_canvas"):
            self.chat_list_canvas.configure(bg=colors["sidebar"], highlightbackground=colors["sidebar"])
            self.chat_list_inner.configure(bg=colors["sidebar"])
            self.recent_count_label.configure(bg=colors["panel2"], fg=colors["muted"])
            self._restyle_chat_cards()
        for checkbox, background_key in getattr(self, "purple_checkboxes", []):
            checkbox.set_colors(colors.get(background_key, colors["panel"]), colors["text"], colors["check_accent"], colors["check_border"])
        self.chat_view.tag_configure("body", foreground=colors["text"], spacing1=3, spacing3=10)
        self.chat_view.tag_configure("user_body", foreground=colors["text"], lmargin1=190, lmargin2=100, rmargin=14, justify="right", spacing1=3, spacing3=18)
        self.chat_view.tag_configure("assistant_body", foreground=colors["text"], lmargin1=8, lmargin2=8, rmargin=170, spacing1=3, spacing3=18)
        self.chat_view.tag_configure("user_name", foreground=colors["accent"], font=(self.font_family, 10, "bold"), lmargin1=190, lmargin2=100, rmargin=14, justify="right", spacing1=10)
        self.chat_view.tag_configure("assistant_name", foreground=colors["success"], font=(self.font_family, 10, "bold"), lmargin1=8, lmargin2=8, rmargin=170, spacing1=10)
        self.chat_view.tag_configure("meta", foreground=colors["muted"], font=(self.font_family, 8, "italic"))
        self.chat_view.tag_configure("error", foreground=colors["danger"])
        self.chat_view.tag_configure("welcome_title", foreground=colors["text"], font=(self.font_family, 23, "bold"), spacing1=12, spacing3=10)
        self.chat_view.tag_configure("welcome_subtitle", foreground=colors["muted"], font=(self.font_family, 10), spacing3=14)
        self.chat_view.tag_configure("quick_prompt", foreground=colors["accent"], underline=True, font=(self.font_family, 10, "bold"), spacing1=5, spacing3=6)
        self.chat_view.tag_bind("quick_prompt", "<Enter>", lambda _e: self.chat_view.configure(cursor="hand2"))
        self.chat_view.tag_bind("quick_prompt", "<Leave>", lambda _e: self.chat_view.configure(cursor=""))
        self.chat_view.tag_bind("quick_prompt", "<Button-1>", self._quick_prompt_click)

    def _apply_high_dpi_windows_icon(self) -> None:
        """Set explicit large/small Win32 icons for crisp taskbar and Alt+Tab rendering."""
        if os.name != "nt":
            return
        try:
            icon_path = str(resource_path("app_icon.ico"))
            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            load_from_file = 0x0010
            image_icon = 1
            hwnd = ctypes.c_void_p(self.root.winfo_id())
            for metric, icon_type in ((11, 1), (49, 0)):
                size = int(user32.GetSystemMetrics(metric)) or (32 if icon_type else 16)
                handle = user32.LoadImageW(None, icon_path, image_icon, size, size, load_from_file)
                if handle:
                    user32.SendMessageW(hwnd, 0x0080, ctypes.c_void_p(icon_type), ctypes.c_void_p(handle))
                    self._win32_icon_handles = getattr(self, "_win32_icon_handles", []) + [handle]
        except Exception:
            pass

    def _apply_windows_titlebar_theme(self) -> None:
        """Ask DWM to draw a dark native Windows title bar when supported."""
        if os.name != "nt":
            return
        try:
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
            dark = 1 if self.config.get("theme", "Тёмная") != "Светлая" else 0
            value = ctypes.c_int(dark)
            size = ctypes.sizeof(value)
            # Attribute 20 is supported by current Windows 10/11; 19 is the
            # compatibility identifier used by earlier Windows 10 builds.
            result = dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), size)
            if result != 0:
                dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), size)
            if dark:
                caption = ctypes.c_uint(0x0010120B)  # deep navy caption (COLORREF)
                text_color = ctypes.c_uint(0x00ECF2FC)
                border = ctypes.c_uint(0x0026364E)
            else:
                caption = ctypes.c_uint(0xFFFFFFFF)  # system default
                text_color = ctypes.c_uint(0xFFFFFFFF)
                border = ctypes.c_uint(0xFFFFFFFF)
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
            dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
            dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
        except Exception:
            # Unsupported DWM attributes must never prevent the app from starting.
            return

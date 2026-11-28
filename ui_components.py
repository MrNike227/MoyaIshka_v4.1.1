# -*- coding: utf-8 -*-
"""Reusable Tkinter UI components for ISH."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

class PurpleCheckbox(tk.Frame):
    """Accessible click/keyboard checkbox with a solid purple square when enabled."""

    def __init__(self, master: tk.Misc, text: str, variable: tk.BooleanVar, command=None, *,
                 font=None, wraplength: int = 860, background: str = "#17243A",
                 foreground: str = "#ECF2FC", accent: str = "#4B356F",
                 border: str = "#8B7AA6") -> None:
        super().__init__(master, bg=background, bd=0, highlightthickness=0, takefocus=1)
        self.variable = variable
        self.command = command
        self._background = background
        self._foreground = foreground
        self._accent = accent
        self._border = border
        self.indicator = tk.Canvas(self, width=24, height=24, bg=background, bd=0,
                                   highlightthickness=0, cursor="hand2")
        self.indicator.pack(side="left", padx=(0, 8), pady=2)
        self.caption = tk.Label(self, text=text, bg=background, fg=foreground,
                                font=font, anchor="w", justify="left",
                                wraplength=wraplength, cursor="hand2")
        self.caption.pack(side="left", fill="x", expand=True)
        for widget in (self, self.indicator, self.caption):
            widget.bind("<Button-1>", self._toggle)
            widget.bind("<space>", self._toggle)
            widget.bind("<Return>", self._toggle)
        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)
        self._trace_id = self.variable.trace_add("write", self._draw)
        self._draw()

    def _draw(self, *_args) -> None:
        if not self.winfo_exists():
            return
        self.indicator.delete("all")
        selected = bool(self.variable.get())
        fill = self._accent if selected else self._background
        outline = self._accent if selected else self._border
        # A filled square means YES; an empty outlined square means NO.
        self.indicator.create_rectangle(4, 4, 19, 19, fill=fill, outline=outline, width=1.5)

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        self._draw()
        if callable(self.command):
            self.command()
        return "break"

    def _hover_on(self, _event=None) -> None:
        try:
            self.caption.configure(fg=self._accent if not bool(self.variable.get()) else self._foreground)
        except tk.TclError:
            pass

    def _hover_off(self, _event=None) -> None:
        try:
            self.caption.configure(fg=self._foreground)
        except tk.TclError:
            pass

    def set_colors(self, background: str, foreground: str, accent: str, border: str) -> None:
        self._background = background
        self._foreground = foreground
        self._accent = accent
        self._border = border
        self.configure(bg=background)
        self.indicator.configure(bg=background)
        self.caption.configure(bg=background, fg=foreground)
        self._draw()

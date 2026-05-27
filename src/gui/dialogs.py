"""Reusable dialog helpers."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple


def ask_confirm(title: str, message: str) -> bool:
    return messagebox.askyesno(title, message)


def show_error(title: str, message: str) -> None:
    messagebox.showerror(title, message)


def show_info(title: str, message: str) -> None:
    messagebox.showinfo(title, message)


class FormDialog(tk.Toplevel):
    """Generic modal form dialog with labeled fields."""

    def __init__(self, parent: tk.Widget, title: str,
                 fields: List[Dict], on_save: Callable[[Dict], None],
                 initial: Optional[Dict] = None) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self._fields = fields
        self._on_save = on_save
        self._vars: Dict[str, tk.Variable] = {}
        self._widgets: Dict[str, tk.Widget] = {}
        self._build(initial or {})

    def _build(self, initial: Dict) -> None:
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        for row_idx, fld in enumerate(self._fields):
            key = fld["key"]
            label = fld.get("label", key.replace("_", " ").title())
            ftype = fld.get("type", "entry")

            ttk.Label(frame, text=f"{label}:").grid(
                row=row_idx, column=0, sticky=tk.W, padx=(0, 10), pady=4)

            if ftype == "combobox":
                var = tk.StringVar(value=str(initial.get(key, fld.get("default", ""))))
                cb = ttk.Combobox(frame, textvariable=var,
                                  values=fld.get("values", []), state="readonly", width=26)
                cb.grid(row=row_idx, column=1, pady=4, sticky=tk.W)
                self._vars[key] = var
                self._widgets[key] = cb
            elif ftype == "text":
                var = tk.StringVar(value=str(initial.get(key, "")))
                txt = tk.Text(frame, width=28, height=3, wrap=tk.WORD)
                txt.insert("1.0", initial.get(key, ""))
                txt.grid(row=row_idx, column=1, pady=4)
                self._widgets[key] = txt
                self._vars[key] = var  # placeholder
            elif ftype == "checkbutton":
                var = tk.BooleanVar(value=bool(initial.get(key, fld.get("default", False))))
                ttk.Checkbutton(frame, variable=var).grid(
                    row=row_idx, column=1, pady=4, sticky=tk.W)
                self._vars[key] = var
            else:
                var = tk.StringVar(value=str(initial.get(key, fld.get("default", ""))))
                show = "•" if fld.get("password") else ""
                entry = ttk.Entry(frame, textvariable=var, width=28, show=show)
                entry.grid(row=row_idx, column=1, pady=4)
                self._vars[key] = var
                self._widgets[key] = entry

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(self._fields), column=0, columnspan=2, pady=(16, 0))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self.bind("<Return>", lambda _: self._save())

    def _save(self) -> None:
        data: Dict[str, Any] = {}
        for fld in self._fields:
            key = fld["key"]
            ftype = fld.get("type", "entry")
            if ftype == "text":
                w = self._widgets.get(key)
                data[key] = w.get("1.0", tk.END).strip() if w else ""
            elif ftype == "checkbutton":
                data[key] = bool(self._vars[key].get())
            else:
                data[key] = self._vars[key].get()
        self._on_save(data)


class SearchableListDialog(tk.Toplevel):
    """A searchable list dialog for picking one item."""

    def __init__(self, parent: tk.Widget, title: str, items: List[Tuple[Any, str]],
                 on_select: Callable[[Any], None]) -> None:
        """
        Args:
            items: List of (value, display_label) tuples.
            on_select: Called with the selected value.
        """
        super().__init__(parent)
        self.title(title)
        self.grab_set()
        self._all_items = items
        self._on_select = on_select
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(frame, textvariable=self._search_var, width=40).pack(fill=tk.X, pady=(0, 6))

        self._listbox = tk.Listbox(frame, width=50, height=15, selectmode=tk.SINGLE)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._filtered: List[Tuple[Any, str]] = list(self._all_items)
        self._refresh_list()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_frame, text="Select", command=self._select).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)
        self._listbox.bind("<Double-Button-1>", lambda _: self._select())

    def _filter(self) -> None:
        q = self._search_var.get().lower()
        self._filtered = [(v, l) for v, l in self._all_items if q in l.lower()]
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._listbox.delete(0, tk.END)
        for _, label in self._filtered:
            self._listbox.insert(tk.END, label)

    def _select(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        value, _ = self._filtered[sel[0]]
        self._on_select(value)
        self.destroy()

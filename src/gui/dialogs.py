"""Reusable dialog widgets for the application."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple


def show_error(title: str, message: str) -> None:
    """Show a standard error dialog."""
    messagebox.showerror(title, message)


def show_info(title: str, message: str) -> None:
    """Show a standard info dialog."""
    messagebox.showinfo(title, message)


def ask_yes_no(title: str, message: str) -> bool:
    """Show a yes/no dialog and return the result."""
    return messagebox.askyesno(title, message)


class FormDialog(tk.Toplevel):
    """Generic modal form dialog.

    Subclass and override :meth:`_build_form` to add fields, then call
    :meth:`get_data` to retrieve submitted values.

    Args:
        master: Parent widget.
        title:  Window title.
    """

    def __init__(self, master: tk.Misc, title: str = "Form") -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self._result: Optional[Dict] = None
        self._vars: Dict[str, tk.Variable] = {}

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        self._form_frame = ttk.Frame(frame)
        self._form_frame.pack(fill=tk.BOTH, expand=True)

        self._build_form(self._form_frame)

        sep = ttk.Separator(frame, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, pady=10)

        btn = ttk.Frame(frame)
        btn.pack(fill=tk.X)
        ttk.Button(btn, text="Save", command=self._on_save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        self._center()
        self.wait_window(self)

    def _build_form(self, frame: ttk.Frame) -> None:
        """Override to add labeled form rows."""

    def _on_save(self) -> None:
        """Collect variable values and close."""
        self._result = {k: v.get() for k, v in self._vars.items()}
        self.destroy()

    def get_data(self) -> Optional[Dict]:
        """Return submitted form data or ``None`` if cancelled."""
        return self._result

    def _add_field(
        self,
        frame: ttk.Frame,
        label: str,
        key: str,
        row: int,
        var_type: type = tk.StringVar,
        widget_type: type = ttk.Entry,
        options: Optional[List] = None,
        default: Any = "",
    ) -> tk.Variable:
        """Add a labeled field to the form.

        Args:
            frame:       Container frame.
            label:       Label text.
            key:         Dict key for result.
            row:         Grid row index.
            var_type:    Tkinter variable class.
            widget_type: Widget class to instantiate.
            options:     For Combobox: list of values.
            default:     Default variable value.

        Returns:
            The created Tkinter variable.
        """
        ttk.Label(frame, text=label + ":").grid(row=row, column=0, sticky=tk.W, pady=3, padx=(0, 8))
        var = var_type(value=default)
        self._vars[key] = var
        if widget_type == ttk.Combobox and options is not None:
            w = ttk.Combobox(frame, textvariable=var, values=options, state="readonly", width=28)
        elif widget_type == ttk.Entry:
            w = ttk.Entry(frame, textvariable=var, width=30)
        else:
            w = widget_type(frame, textvariable=var, width=30)
        w.grid(row=row, column=1, sticky=tk.EW, pady=3)
        frame.columnconfigure(1, weight=1)
        return var

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")


class ConfirmDialog(tk.Toplevel):
    """Simple yes/no confirmation dialog returning a boolean."""

    def __init__(self, master: tk.Misc, title: str, message: str) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.result = False

        ttk.Label(self, text=message, wraplength=400, padding=20).pack()
        btn = ttk.Frame(self, padding=(0, 0, 10, 10))
        btn.pack(fill=tk.X)
        ttk.Button(btn, text="Yes", command=self._yes).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn, text="No", command=self.destroy).pack(side=tk.RIGHT)

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")
        self.wait_window(self)

    def _yes(self) -> None:
        self.result = True
        self.destroy()


class SearchableCombobox(ttk.Frame):
    """A combobox with a live filter as the user types.

    Args:
        master:   Parent widget.
        values:   Full list of string options.
        **kwargs: Forwarded to the underlying ttk.Entry.
    """

    def __init__(self, master: tk.Misc, values: List[str], **kwargs: Any) -> None:
        super().__init__(master)
        self._all_values = values
        self._var = tk.StringVar()
        self._var.trace_add("write", self._on_key)
        self._entry = ttk.Entry(self, textvariable=self._var, **kwargs)
        self._entry.pack(fill=tk.X)
        self._listbox_frame: Optional[tk.Toplevel] = None

    def get(self) -> str:
        """Return current text value."""
        return self._var.get()

    def set(self, value: str) -> None:
        """Set the text value."""
        self._var.set(value)

    def _on_key(self, *_: Any) -> None:
        text = self._var.get().lower()
        filtered = [v for v in self._all_values if text in v.lower()]
        self._show_dropdown(filtered[:10])

    def _show_dropdown(self, items: List[str]) -> None:
        if self._listbox_frame:
            self._listbox_frame.destroy()
        if not items:
            return
        self._listbox_frame = tk.Toplevel(self)
        self._listbox_frame.wm_overrideredirect(True)
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        self._listbox_frame.geometry(f"+{x}+{y}")
        lb = tk.Listbox(self._listbox_frame, height=min(len(items), 8))
        lb.pack()
        for item in items:
            lb.insert(tk.END, item)
        lb.bind("<<ListboxSelect>>", lambda e: self._select(lb))

    def _select(self, lb: tk.Listbox) -> None:
        sel = lb.curselection()
        if sel:
            self._var.set(lb.get(sel[0]))
        if self._listbox_frame:
            self._listbox_frame.destroy()
            self._listbox_frame = None

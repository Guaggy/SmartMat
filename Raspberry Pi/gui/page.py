"""Tool windows as Notebook tabs.

A tool window class does `self.window = make_window(parent)`: given a ttk.Notebook it gets a Page (a tab),
given anything else a tk.Toplevel, so the class builds the same way into either. A Page answers the
Toplevel calls the classes make (title, geometry, protocol, lift, destroy, winfo_exists).
"""

import tkinter as tk
from tkinter import ttk

from gui import theme


def make_window(parent):
    """A Page in parent when parent is a ttk.Notebook, otherwise a tk.Toplevel of parent"""
    return Page(parent) if isinstance(parent, ttk.Notebook) else tk.Toplevel(parent)


def is_shown(window):
    """The window exists and is on screen: a Toplevel always, a Page only while its tab is selected"""
    if not window.winfo_exists():
        return False
    return not isinstance(window, Page) or window.selected()


def selected_page(notebook):
    """The Page of the selected tab, or None (e.g. the Live tab)"""
    tab = notebook.select()
    widget = notebook.nametowidget(tab) if tab else None
    return widget if isinstance(widget, Page) else None


class Page(ttk.Frame):
    """One closable tab"""

    def __init__(self, notebook):
        super().__init__(notebook)
        self.notebook = notebook
        self._on_close = None
        notebook.add(self, text="")
        notebook.select(self)

    def title(self, text=None):
        if text is None:
            return self.notebook.tab(self, "text")
        self.notebook.tab(self, text=text)

    def geometry(self, *_args):
        """A tab takes the notebook's size"""

    def protocol(self, name=None, func=None):
        if name == "WM_DELETE_WINDOW":
            self._on_close = func

    def lift(self, *_args):
        self.notebook.select(self)

    def selected(self):
        return self.notebook.select() == str(self)

    def close(self):
        (self._on_close or self.destroy)()

    def destroy(self):
        """Removes the tab (a destroyed notebook child leaves the notebook) and its figures from the theme"""
        super().destroy()
        theme.prune_figures()


def tab_actions(notebook, on_pop_out, hidden_style="Bare.TNotebook"):
    """Pop out / Close for the selected Page, at the right end of the tab strip (not while the notebook is in
    hidden_style, which hides the strip). on_pop_out(page) rebuilds the page's tool in its own window."""
    bar = ttk.Frame(notebook.master)  # made after the notebook, so drawn above it
    ttk.Button(bar, text="Pop out", style="Toolbutton",
               command=lambda: on_pop_out(selected_page(notebook))).pack(side=tk.LEFT)
    ttk.Button(bar, text="Close", style="Toolbutton",
               command=lambda: selected_page(notebook).close()).pack(side=tk.LEFT)

    def update(_event=None):
        if selected_page(notebook) is None or str(notebook.cget("style")) == hidden_style:
            bar.place_forget()
        else:
            bar.place(in_=notebook, relx=1.0, x=-2, y=0, anchor="ne")
    notebook.bind("<<NotebookTabChanged>>", update, add="+")
    return bar

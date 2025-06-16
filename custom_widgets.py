import tkinter as tk
from tkinter import ttk, filedialog, messagebox

CONFIG_FILE = "ktools_ui_config.ini"

class AutoScrollbar(tk.Scrollbar):
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        tk.Scrollbar.set(self, lo, hi)
    def pack(self, **kw):
        raise tk.TclError("cannot use pack with this widget")
    def place(self, **kw):
        raise tk.TclError("cannot use place with this widget")

class CustomTooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)
    def show_tooltip(self, event):
        if self.tooltip:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, background="lightyellow", relief="solid", borderwidth=1)
        label.pack()
    def hide_tooltip(self, event):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class FileFolderSelector():
    def __init__(self, parent, label_text, var, config, key, row, select_type="folder", filetypes=None):
        self.var = var
        self.key = key
        self.config = config
        self.select_type = select_type
        self.filetypes = filetypes
        self.parent = parent
        
        # Text label 
        self.label = tk.Label(parent, text=label_text, anchor="e")
        self.label.grid(row=row, column=0, sticky="e", padx=2, pady=5)
        
        # Frame: contains Entry and Clear button
        self.entry_frame = tk.Frame(parent, relief="sunken", bd=1)
        self.entry_frame.grid(row=row, column=1, sticky="ew", padx=3, pady=5)
        self.entry_frame.columnconfigure(0, weight=1)
        
        # Folder directory
        self.entry = tk.Entry(self.entry_frame, textvariable=var, relief="flat", bd=0)
        self.entry.grid(row=0, column=0, sticky="ew", ipady=4)
        
        # Clear button
        self.clear_btn = tk.Button(
            self.entry_frame, text="✕", command=self.clear_selection,
            relief="flat", bd=0, width=3, font=("Arial", 8),
            fg="#666666", bg="white"
        )
        self.clear_btn.grid(row=0, column=1, sticky="ns")
        
        # Browse button
        self.button = tk.Button(parent, text="Browse", command=self.select, height=1)
        self.button.grid(row=row, column=2, padx=5, sticky="nsew", pady=5)

    def select(self):
        if self.select_type == "file":
            path = filedialog.askopenfilename(filetypes=self.filetypes)
        elif self.select_type == "files":
            path = filedialog.askopenfilenames(filetypes=self.filetypes)
        else:
            path = filedialog.askdirectory()
        if path:
            if isinstance(path, tuple):
                self.var.set(",".join(path))
            else:
                self.var.set(path)
            self.save_config()

    def clear_selection(self):
        self.var.set("")
        self.save_config()

    def save_config(self):
        if not self.config.has_section("folders"):
            self.config.add_section("folders")
        self.config.set("folders", self.key, self.var.get())
        with open(CONFIG_FILE, "w") as f:
            self.config.write(f)
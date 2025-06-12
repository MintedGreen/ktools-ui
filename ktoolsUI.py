import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import threading
import configparser

CONFIG_FILE = "tex2png_config.ini"

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

class KtechTab:
    def __init__(self, parent, config):
        self.parent = parent
        self.config = config
        last_ktech = self.config.get("folders", "ktech", fallback="")
        last_output = self.config.get("folders", "output", fallback="")

        parent.grid_columnconfigure(0, minsize=130)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, minsize=80)
        parent.grid_rowconfigure(0, minsize=38)
        parent.grid_rowconfigure(1, minsize=38)

        # ktech folder
        tk.Label(parent, text="ktech folder:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.ktech_dir_var = tk.StringVar(value=last_ktech)
        self.ktech_entry = tk.Entry(parent, textvariable=self.ktech_dir_var)
        self.ktech_entry.grid(row=0, column=1, sticky='ew', padx=5, ipady=6)
        tk.Button(parent, text="Browse", command=self.select_ktech_dir, height=1).grid(row=0, column=2, padx=5, sticky='n')

        # Output folder
        tk.Label(parent, text="Output folder:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.output_dir_var = tk.StringVar(value=last_output)
        self.output_entry = tk.Entry(parent, textvariable=self.output_dir_var)
        self.output_entry.grid(row=1, column=1, sticky='ew', padx=5, ipady=6)
        tk.Button(parent, text="Browse", command=self.select_output_dir, height=1).grid(row=1, column=2, padx=5, sticky='n')

        # .tex files (multi-select) with auto-hiding scrollbar
        tk.Label(parent, text="Select tex files:").grid(row=2, column=0, sticky='ne', padx=5, pady=5)
        self.tex_files = []

        text_frame = tk.Frame(parent)
        text_frame.grid(row=2, column=1, sticky='nsew', padx=5)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.tex_files_text = tk.Text(text_frame, height=7, wrap='none')
        self.tex_files_text.grid(row=0, column=0, sticky='nsew')

        self.scrollbar = AutoScrollbar(text_frame, orient="vertical", command=self.tex_files_text.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.tex_files_text['yscrollcommand'] = self.scrollbar.set

        tk.Button(parent, text="Browse", command=self.select_tex_files).grid(row=2, column=2, padx=5, sticky='n')

        # Skip, Convert, Cancel
        self.skip_var = tk.IntVar(value=0)
        action_frame = tk.Frame(parent)
        action_frame.grid(row=3, column=1, sticky='w', pady=12)
        self.skip_checkbox = tk.Checkbutton(
            action_frame, text="Skip if output PNG exists",
            variable=self.skip_var
        )
        self.skip_checkbox.pack(side='left', padx=(0, 10))
        self.convert_btn = tk.Button(action_frame, text="Convert", command=self.start_convert)
        self.convert_btn.pack(side='left')
        self.cancel_btn = tk.Button(action_frame, text="Cancel", command=self.cancel_convert, state="disabled")
        self.cancel_btn.pack(side='left', padx=(10, 0))

        self.status_frame = tk.Frame(parent)
        self.status_frame.grid(row=4, column=1, columnspan=2, sticky='w', pady=(5, 0))
        self.status_label = tk.Label(self.status_frame, text="", fg="green")
        self.status_label.pack(side='top', anchor='w')
        self.skipped_label = tk.Label(self.status_frame, text="", fg="gray")
        self.skipped_label.pack(side='top', anchor='w', pady=(0, 0))

        self._convert_thread = None
        self._cancel_flag = False
        self._current_proc = None

    def select_ktech_dir(self):
        path = filedialog.askdirectory(title="Select ktech folder")
        if path:
            self.ktech_dir_var.set(path)
            self.save_config()

    def select_output_dir(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir_var.set(path)
            self.save_config()

    def select_tex_files(self):
        paths = filedialog.askopenfilenames(
            title="Select .tex files to convert",
            filetypes=[("Klei TEX files", "*.tex")])
        if paths:
            self.tex_files = list(paths)
            self.tex_files_text.delete("1.0", tk.END)
            for p in self.tex_files:
                self.tex_files_text.insert(tk.END, p + "\n")

    def save_config(self):
        if not self.config.has_section("folders"):
            self.config.add_section("folders")
        self.config.set("folders", "ktech", self.ktech_dir_var.get())
        self.config.set("folders", "output", self.output_dir_var.get())
        with open(CONFIG_FILE, "w") as f:
            self.config.write(f)

    def start_convert(self):
        self.status_label.config(text="Converting...", fg="blue")
        self.skipped_label.config(text="")
        self.convert_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self._cancel_flag = False
        self._convert_thread = threading.Thread(target=self.convert)
        self._convert_thread.start()

    def cancel_convert(self):
        self._cancel_flag = True
        if self._current_proc is not None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self.status_label.config(text="Conversion cancelled.", fg="red")
        self.cancel_btn.config(state="disabled")
        self.convert_btn.config(state="normal")

    def convert(self):
        ktech_dir = self.ktech_dir_var.get()
        output_dir = self.output_dir_var.get()
        skip_existing = self.skip_var.get()
        if not (ktech_dir and output_dir and self.tex_files):
            self.parent.after(0, lambda: messagebox.showerror("Error", "Please select all required folders and files."))
            self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
            self.parent.after(0, lambda: self.status_label.config(text=""))
            self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))
            return

        ktech_exe = os.path.join(ktech_dir, "ktech")
        if os.name == 'nt':
            ktech_exe += ".exe"

        errors = []
        skipped = 0

        for tex_file in self.tex_files:
            if self._cancel_flag:
                break
            base = os.path.splitext(os.path.basename(tex_file))[0]
            out_png = os.path.join(output_dir, base + ".png")
            if skip_existing and os.path.exists(out_png):
                skipped += 1
                continue
            cmd = f'"{ktech_exe}" "{tex_file}" "{output_dir}"'
            try:
                self._current_proc = subprocess.Popen(cmd, shell=True)
                self._current_proc.wait()
                if self._current_proc.returncode != 0:
                    errors.append(base + ".tex")
            except Exception:
                errors.append(base + ".tex")
            finally:
                self._current_proc = None

        if self._cancel_flag:
            self.parent.after(0, lambda: self.status_label.config(text="Conversion cancelled.", fg="red"))
        elif errors:
            self.parent.after(0, lambda: self.status_label.config(
                text=f"Some conversions failed: {', '.join(errors)}", fg="red"))
        else:
            self.parent.after(0, lambda: self.status_label.config(text="All conversions completed!", fg="green"))

        if skipped > 0:
            self.parent.after(0, lambda: self.skipped_label.config(
                text=f"Skipped {skipped} file(s) because PNG already exists."))
        else:
            self.parent.after(0, lambda: self.skipped_label.config(text=""))

        self.parent.after(0, self.clear_inputs)
        self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
        self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))

    def clear_inputs(self):
        self.tex_files = []
        self.tex_files_text.delete("1.0", tk.END)

class KraneTab:
    def __init__(self, parent, config, ktech_tab_ref):
        self.parent = parent
        self.config = config
        self.ktech_tab_ref = ktech_tab_ref
        last_krane = self.config.get("folders", "krane", fallback=ktech_tab_ref.ktech_dir_var.get() if ktech_tab_ref else "")

        parent.grid_columnconfigure(0, minsize=130)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, minsize=80)
        parent.grid_rowconfigure(0, minsize=38)

        # krane folder
        tk.Label(parent, text="krane folder:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.krane_dir_var = tk.StringVar(value=last_krane)
        self.krane_entry = tk.Entry(parent, textvariable=self.krane_dir_var)
        self.krane_entry.grid(row=0, column=1, sticky='ew', padx=5, ipady=6)
        tk.Button(parent, text="Browse", command=self.select_krane_dir, height=1).grid(row=0, column=2, padx=5, sticky='n')

        # anim folders (單一資料夾選擇，每次選一個，可多次)
        tk.Label(parent, text="Select anim folders:").grid(row=1, column=0, sticky='ne', padx=5, pady=5)
        self.anim_folders = []

        text_frame = tk.Frame(parent)
        text_frame.grid(row=1, column=1, sticky='nsew', padx=5)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.anim_folders_text = tk.Text(text_frame, height=7, wrap='none')
        self.anim_folders_text.grid(row=0, column=0, sticky='nsew')

        self.scrollbar = AutoScrollbar(text_frame, orient="vertical", command=self.anim_folders_text.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.anim_folders_text['yscrollcommand'] = self.scrollbar.set

        tk.Button(parent, text="Browse", command=self.select_anim_folder).grid(row=1, column=2, padx=5, sticky='n')

        # Skip, Convert, Cancel
        self.skip_var = tk.IntVar(value=0)
        action_frame = tk.Frame(parent)
        action_frame.grid(row=2, column=1, sticky='w', pady=12)
        self.skip_checkbox = tk.Checkbutton(
            action_frame, text="Skip if output files exist",
            variable=self.skip_var
        )
        self.skip_checkbox.pack(side='left', padx=(0, 10))
        self.convert_btn = tk.Button(action_frame, text="Convert", command=self.start_convert)
        self.convert_btn.pack(side='left')
        self.cancel_btn = tk.Button(action_frame, text="Cancel", command=self.cancel_convert, state="disabled")
        self.cancel_btn.pack(side='left', padx=(10, 0))

        self.status_frame = tk.Frame(parent)
        self.status_frame.grid(row=3, column=1, columnspan=2, sticky='w', pady=(5, 0))
        self.status_label = tk.Label(self.status_frame, text="", fg="green")
        self.status_label.pack(side='top', anchor='w')
        self.skipped_label = tk.Label(self.status_frame, text="", fg="gray")
        self.skipped_label.pack(side='top', anchor='w', pady=(0, 0))

        self._convert_thread = None
        self._cancel_flag = False
        self._current_proc = None

    def select_krane_dir(self):
        path = filedialog.askdirectory(title="Select krane folder")
        if path:
            self.krane_dir_var.set(path)
            self.save_config()

    def select_anim_folder(self):
        path = filedialog.askdirectory(title="Select an anim folder")
        if path and path not in self.anim_folders:
            self.anim_folders.append(path)
            self.anim_folders_text.insert(tk.END, path + "\n")

    def save_config(self):
        if not self.config.has_section("folders"):
            self.config.add_section("folders")
        self.config.set("folders", "krane", self.krane_dir_var.get())
        with open(CONFIG_FILE, "w") as f:
            self.config.write(f)

    def start_convert(self):
        self.status_label.config(text="Converting...", fg="blue")
        self.skipped_label.config(text="")
        self.convert_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self._cancel_flag = False
        self._convert_thread = threading.Thread(target=self.convert)
        self._convert_thread.start()

    def cancel_convert(self):
        self._cancel_flag = True
        if self._current_proc is not None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self.status_label.config(text="Conversion cancelled.", fg="red")
        self.cancel_btn.config(state="disabled")
        self.convert_btn.config(state="normal")

    def convert(self):
        krane_dir = self.krane_dir_var.get()
        skip_existing = self.skip_var.get()
        if not (krane_dir and self.anim_folders):
            self.parent.after(0, lambda: messagebox.showerror("Error", "Please select krane folder and anim folders."))
            self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
            self.parent.after(0, lambda: self.status_label.config(text=""))
            self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))
            return

        krane_exe = os.path.join(krane_dir, "krane")
        if os.name == 'nt':
            krane_exe += ".exe"

        errors = []
        skipped = 0

        for folder in self.anim_folders:
            if self._cancel_flag:
                break
            output_dir = os.path.join(folder, "output")
            os.makedirs(output_dir, exist_ok=True)
            scim_files = [f for f in os.listdir(output_dir) if f.endswith(".scim")]
            if skip_existing and scim_files:
                skipped += 1
                continue
            cmd = f'"{krane_exe}" "{folder}" "{output_dir}"'
            try:
                self._current_proc = subprocess.Popen(cmd, shell=True)
                self._current_proc.wait()
                if self._current_proc.returncode != 0:
                    errors.append(os.path.basename(folder))
            except Exception:
                errors.append(os.path.basename(folder))
            finally:
                self._current_proc = None

        if self._cancel_flag:
            self.parent.after(0, lambda: self.status_label.config(text="Conversion cancelled.", fg="red"))
        elif errors:
            self.parent.after(0, lambda: self.status_label.config(
                text=f"Some conversions failed: {', '.join(errors)}", fg="red"))
        else:
            self.parent.after(0, lambda: self.status_label.config(text="All conversions completed!", fg="green"))

        if skipped > 0:
            self.parent.after(0, lambda: self.skipped_label.config(
                text=f"Skipped {skipped} folder(s) because output files already exist."))
        else:
            self.parent.after(0, lambda: self.skipped_label.config(text=""))

        self.parent.after(0, self.clear_inputs)
        self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
        self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))

    def clear_inputs(self):
        self.anim_folders = []
        self.anim_folders_text.delete("1.0", tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("KTools - Multi Converter")
    root.geometry("900x500")
    root.minsize(820, 420)
    root.option_add("*Font", "Arial 12")

    # 分頁標籤字體放大但不粗體
    style = ttk.Style()
    style.configure('TNotebook.Tab', font=('Arial', 16))  # 不加 bold

    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True)

    # ktech 分頁
    frame_ktech = tk.Frame(notebook)
    notebook.add(frame_ktech, text="ktech")
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    ktech_tab = KtechTab(frame_ktech, config)

    # krane 分頁
    frame_krane = tk.Frame(notebook)
    notebook.add(frame_krane, text="krane")
    KraneTab(frame_krane, config, ktech_tab)

    root.mainloop()

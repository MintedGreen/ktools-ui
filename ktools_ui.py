import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import threading
import configparser
from idlelib.tooltip import Hovertip
from PIL import Image
import xml.etree.ElementTree as ET
from custom_widgets import AutoScrollbar, FileFolderSelector

CONFIG_FILE = "ktools_ui_config.ini"
KTECH_SOURCE = "ktech_source"
KTECH_OUTPUT = "ktech_output"
KRANE_SOURCE = "krane_source"
CROP_SOURCE = "crop_source"
CROP_OUTPUT = "crop_output"

class BaseTab(tk.Frame):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.setup_common_ui()
        # 其他共用初始化

    def setup_common_ui(self):
        # 建立進度區、狀態標籤、檔案選擇等
        pass

    def select_file(self, var, filetypes):
        # 通用檔案選擇邏輯
        pass

    def update_status(self, text, color):
        # 統一狀態更新
        pass

class KtechTab(BaseTab):
    def __init__(self, parent, config):
        super().__init__(parent, config)
        last_ktech = self.config.get("folders", KTECH_SOURCE, fallback="")
        last_output = self.config.get("folders", KTECH_OUTPUT, fallback="")

        self.parent.grid_columnconfigure(0, weight=0, minsize=80)
        self.parent.grid_columnconfigure(1, weight=1, minsize=120)
        self.parent.grid_columnconfigure(2, weight=0, minsize=80)
        self.parent.grid_rowconfigure(0, minsize=38)
        parent.grid_rowconfigure(1, minsize=38)

        self.ktech_dir_var = tk.StringVar(value=last_ktech)
        self.ktech_selector = FileFolderSelector(
            parent, "ktech folder", self.ktech_dir_var, config=self.config, key=KTECH_SOURCE, row=0
        )

        self.output_dir_var = tk.StringVar(value=last_output)
        self.output_selector = FileFolderSelector(
            parent, "Output folder", self.output_dir_var, config=self.config, key=KTECH_OUTPUT, row=1
        )

        tk.Label(parent, text="Tex files").grid(row=2, column=0, sticky='ne', padx=2, pady=5)
        self.tex_files = []

        text_frame = tk.Frame(parent)
        text_frame.grid(row=2, column=1, sticky='nsew', padx=3, pady=5)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.tex_files_text = tk.Text(text_frame, height=7, wrap='none')
        self.tex_files_text.grid(row=0, column=0, sticky='nsew')

        self.scrollbar = AutoScrollbar(text_frame, orient="vertical", command=self.tex_files_text.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.tex_files_text['yscrollcommand'] = self.scrollbar.set

        tk.Button(parent, text="Browse", command=self.select_tex_files).grid(row=2, column=2, padx=5, pady=5, sticky='n')

        self.skip_var = tk.IntVar(value=0)
        action_frame = tk.Frame(parent)
        action_frame.grid(row=3, column=1, sticky='w', pady=12)

        self.skip_checkbox = tk.Checkbutton(
            action_frame, text="Skip if output png files exist",
            variable=self.skip_var
        )
        self.skip_checkbox.pack(side='left', padx=(0, 10))

        self.convert_btn = tk.Button(action_frame, text="Convert", command=self.start_convert)
        self.convert_btn.pack(side='left')
        self.cancel_btn = tk.Button(action_frame, text="Cancel", command=self.cancel_convert, state="disabled")
        self.cancel_btn.pack(side='left', padx=(10, 0))

        # Progress frame with scrollable text
        self.status_frame = tk.Frame(parent)
        self.status_frame.grid(row=4, column=1, columnspan=2, sticky='nsew', pady=(5, 0))
        self.status_label = tk.Label(self.status_frame, text="", fg="green")
        self.status_label.pack(side='top', anchor='w')

        self.skipped_label = tk.Label(self.status_frame, text="", fg="gray")
        self.skipped_label.pack(side='top', anchor='w', pady=(0, 0))

        self._convert_thread = None
        self._cancel_flag = False
        self._current_proc = None

    def select_tex_files(self):
        paths = filedialog.askopenfilenames(
            title="Select .tex files to convert",
            filetypes=[("Klei TEX files", "*.tex")])
        if paths:
            self.tex_files = list(paths)
            self.tex_files_text.config(state='normal')
            self.tex_files_text.delete("1.0", tk.END)
            for p in self.tex_files:
                self.tex_files_text.insert(tk.END, os.path.basename(p) + "\n")
            self.tex_files_text.config(state='disabled')

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

    def update_progress(self, idx, text):
        self.tex_files_text.config(state='normal')
        self.tex_files_text.delete(f"{idx+1}.0", f"{idx+1}.end")
        self.tex_files_text.insert(f"{idx+1}.0", text)
        self.tex_files_text.config(state='disabled')

    def convert(self):
        ktech_dir = self.ktech_dir_var.get()
        output_dir = self.output_dir_var.get()
        skip_existing = self.skip_var.get()
        if not output_dir:
            self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
            self.parent.after(0, lambda: self.status_label.config(text="Please select output folder.", fg="red"))
            self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))
            return
        if not self.tex_files:
            self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
            self.parent.after(0, lambda: self.status_label.config(text="Please select tex files to convert.", fg="red"))
            self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))
            self.tex_files_text.config(state='normal')
            self.tex_files_text.delete("1.0", tk.END)
            self.tex_files_text.config(state='disabled')
            return
        if ktech_dir:
            ktech_exe = os.path.join(ktech_dir, "ktech")
            if os.name == 'nt':
                ktech_exe += ".exe"
        else:
            ktech_exe = "ktech"
        errors = []
        skipped = 0
        for idx, tex_file in enumerate(self.tex_files):
            if self._cancel_flag:
                break
            base = os.path.splitext(os.path.basename(tex_file))[0]
            out_png = os.path.join(output_dir, base + ".png")
            line = f"{base}.tex - converting..."
            self.parent.after(0, lambda i=idx, l=line: self.update_progress(i, l))
            if skip_existing and os.path.exists(out_png):
                skipped += 1
                line = f"{base}.tex - skipped"
                self.parent.after(0, lambda i=idx, l=line: self.update_progress(i, l))
                continue
            cmd = f'"{ktech_exe}" "{tex_file}" "{output_dir}"'
            try:
                self._current_proc = subprocess.Popen(cmd, shell=True)
                self._current_proc.wait()
                if self._current_proc.returncode != 0:
                    errors.append(base + ".tex")
                    line = f"{base}.tex - failed!"
                else:
                    line = f"{base}.tex - success!"
            except Exception:
                errors.append(base + ".tex")
                line = f"{base}.tex - failed!"
            finally:
                self._current_proc = None
            self.parent.after(0, lambda i=idx, l=line: self.update_progress(i, l))
        if self._cancel_flag:
            self.parent.after(0, lambda: self.status_label.config(text="Conversion cancelled.", fg="red"))
        elif errors:
            self.parent.after(0, lambda: self.status_label.config(
                text=f"Some conversions failed: {', '.join(errors)}", fg="red"))
        else:
            self.parent.after(0, lambda: self.status_label.config(text="All conversions completed!", fg="green"))
        if skipped > 0:
            self.parent.after(0, lambda: self.skipped_label.config(
                text=f"Skipped {skipped} file(s) because png already exists."))
        else:
            self.parent.after(0, lambda: self.skipped_label.config(text=""))
        self.parent.after(0, self.clear_inputs)
        self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
        self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))

    def clear_inputs(self):
        self.tex_files = []

class KraneTab:
    def __init__(self, parent, config, ktech_tab_ref):
        self.parent = parent
        self.config = config
        self.ktech_tab_ref = ktech_tab_ref
        last_krane = self.config.get("folders", KRANE_SOURCE, fallback=ktech_tab_ref.ktech_dir_var.get() if ktech_tab_ref else "")

        parent.grid_columnconfigure(0, minsize=130)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, minsize=80)
        parent.grid_rowconfigure(0, minsize=38)

        self.krane_dir_var = tk.StringVar(value=last_krane)
        self.krane_selector = FileFolderSelector(
            parent, "krane folder", self.krane_dir_var, config=self.config, key=KRANE_SOURCE, row=0
        )

        tk.Label(parent, text="Anim folders").grid(row=1, column=0, sticky='ne', padx=5, pady=5)
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

        self.skip_var = tk.IntVar(value=0)
        action_frame = tk.Frame(parent)
        action_frame.grid(row=2, column=1, sticky='w', pady=12)
        self.skip_checkbox = tk.Checkbutton(
            action_frame, text="Skip if output scml files exist",
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
        self.progress_label = tk.Label(self.status_frame, text="", fg="black", justify="left", anchor="w")
        self.progress_label.pack(side='top', anchor='w')
        self.skipped_label = tk.Label(self.status_frame, text="", fg="gray")
        self.skipped_label.pack(side='top', anchor='w', pady=(0, 0))
        self._convert_thread = None
        self._cancel_flag = False
        self._current_proc = None
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
        self.progress_label.config(text="")
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
        if not self.anim_folders:
            self.parent.after(0, lambda: messagebox.showerror("Error", "Please select krane folder and anim folders."))
            self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
            self.parent.after(0, lambda: self.status_label.config(text=""))
            self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))
            return
        if krane_dir:
            krane_exe = os.path.join(krane_dir, "krane")
            if os.name == 'nt':
                krane_exe += ".exe"
        else:
            krane_exe = "krane"
        errors = []
        skipped = 0
        progress_lines = []
        for folder in self.anim_folders:
            if self._cancel_flag:
                break
            output_dir = os.path.join(folder, "output")
            os.makedirs(output_dir, exist_ok=True)
            scml_files = [f for f in os.listdir(output_dir) if f.endswith(".scml")]
            line = f"{os.path.basename(folder)} - converting..."
            progress_lines.append(line)
            self.parent.after(0, lambda l="\n".join(progress_lines): self.progress_label.config(text=l))
            if skip_existing and scml_files:
                skipped += 1
                progress_lines[-1] = f"{os.path.basename(folder)} - skipped"
                self.parent.after(0, lambda l="\n".join(progress_lines): self.progress_label.config(text=l))
                continue
            cmd = f'"{krane_exe}" "{folder}" "{output_dir}"'
            try:
                self._current_proc = subprocess.Popen(cmd, shell=True)
                self._current_proc.wait()
                if self._current_proc.returncode != 0:
                    errors.append(os.path.basename(folder))
                    progress_lines[-1] = f"{os.path.basename(folder)} - failed!"
                else:
                    progress_lines[-1] = f"{os.path.basename(folder)} - success!"
            except Exception:
                errors.append(os.path.basename(folder))
                progress_lines[-1] = f"{os.path.basename(folder)} - failed!"
            finally:
                self._current_proc = None
            self.parent.after(0, lambda l="\n".join(progress_lines): self.progress_label.config(text=l))
        if self._cancel_flag:
            self.parent.after(0, lambda: self.status_label.config(text="Conversion cancelled.", fg="red"))
        elif errors:
            self.parent.after(0, lambda: self.status_label.config(
                text=f"Some conversions failed: {', '.join(errors)}", fg="red"))
        else:
            self.parent.after(0, lambda: self.status_label.config(text="All conversions completed!", fg="green"))
        if skipped > 0:
            self.parent.after(0, lambda: self.skipped_label.config(
                text=f"Skipped {skipped} folder(s) because scml already exists."))
        else:
            self.parent.after(0, lambda: self.skipped_label.config(text=""))
        self.parent.after(0, self.clear_inputs)
        self.parent.after(0, lambda: self.convert_btn.config(state="normal"))
        self.parent.after(0, lambda: self.cancel_btn.config(state="disabled"))

    def clear_inputs(self):
        self.anim_folders = []
        self.anim_folders_text.delete("1.0", tk.END)

class CropTab:
    def __init__(self, parent, config):
        self.parent = parent
        self.config = config
        last_source = self.config.get("folders", CROP_SOURCE, fallback="")
        last_output = self.config.get("folders", CROP_OUTPUT, fallback="")

        parent.grid_columnconfigure(0, minsize=130)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, minsize=80)
        parent.grid_rowconfigure(0, minsize=38)
        parent.grid_rowconfigure(1, minsize=38)
        parent.grid_rowconfigure(2, minsize=38)

        self.source_dir_var = tk.StringVar(value=last_source)
        self.source_selector = FileFolderSelector(
            parent, "Image folder", self.source_dir_var, config=self.config, key=CROP_SOURCE, row=0
        )

        self.output_dir_var = tk.StringVar(value=last_output)
        self.output_selector = FileFolderSelector(
            parent, "Output folder", self.output_dir_var, config=self.config, key=CROP_OUTPUT, row=1
        )

        icon_label = tk.Label(parent, text="Icon names", anchor="ne", justify="right")
        icon_label.grid(row=2, column=0, sticky='ne', padx=5, pady=5)
        self.icon_names_text = tk.Text(parent, height=5, wrap='word')
        self.icon_names_text.grid(row=2, column=1, sticky='nsew', padx=5)
        self.icon_names_scrollbar = AutoScrollbar(parent, orient="vertical", command=self.icon_names_text.yview)
        self.icon_names_scrollbar.grid(row=2, column=1, sticky='nse')
        self.icon_names_text['yscrollcommand'] = self.icon_names_scrollbar.set

        self.force64_var = tk.IntVar(value=0)
        self.force64_checkbox = tk.Checkbutton(parent, text="Force 64px crop", variable=self.force64_var)
        self.force64_checkbox.grid(row=3, column=1, sticky="w", padx=5)

        # checkbox: skip if output files exist
        self.skip_output_var = tk.IntVar(value=0)
        self.skip_output_checkbox = tk.Checkbutton(parent, text="Skip if output files exist", variable=self.skip_output_var)
        self.skip_output_checkbox.grid(row=4, column=1, sticky="w", padx=5)

        action_frame = tk.Frame(parent)
        action_frame.grid(row=5, column=1, sticky='e', pady=12)
        self.crop_btn = tk.Button(action_frame, text="Crop", command=self.crop_icons)
        self.crop_btn.pack(side='right')

        self.status_frame = tk.Frame(parent)
        self.status_frame.grid(row=6, column=1, columnspan=2, sticky='w', pady=(5, 0))
        self.status_label = tk.Label(self.status_frame, text="", fg="green")
        self.status_label.pack(side='top', anchor='w')
        self.progress_label = tk.Label(self.status_frame, text="", fg="black", justify="left", anchor="w")
        self.progress_label.pack(side='top', anchor='w')

    def crop_icons(self):
        source_dir = self.source_dir_var.get()
        output_dir = self.output_dir_var.get()
        icon_names = self.icon_names_text.get("1.0", tk.END).strip()
        force64 = self.force64_var.get() == 1
        skip_output = self.skip_output_var.get() == 1

        if not (source_dir and output_dir and icon_names):
            self.status_label.config(text="Please select source/output folder and enter icon names.", fg="red")
            self.progress_label.config(text="")
            return

        xml_files = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.endswith(".xml")]
        if not xml_files:
            self.status_label.config(text="No XML files found in source folder.", fg="red")
            self.progress_label.config(text="file not found")
            return

        names = [
            n.strip().lower().replace(".tex", "") + ".tex"
            for n in icon_names.replace('\n', ',').split(',')
            if n.strip()
        ]

        found_any = False
        progress_lines = []
        done_names = set()

        for name in names:
            if name in done_names:
                continue
            found = False
            for xml_path in xml_files:
                png_path = os.path.splitext(xml_path)[0] + ".png"
                if not os.path.exists(png_path):
                    # Try to find tex file and convert to png
                    tex_path = os.path.splitext(xml_path)[0] + ".tex"
                    if os.path.exists(tex_path):
                        folder = os.path.dirname(tex_path)
                        ktech_exe = "ktech.exe" if os.name == 'nt' else "ktech"
                        cmd = f'"{ktech_exe}" "{tex_path}" "{folder}"'
                        result = subprocess.run(cmd, shell=True, capture_output=True)
                        if result.returncode != 0 or not os.path.exists(png_path):
                            continue  # Conversion failed, skip
                    else:
                        continue  # No tex file, skip
                image = Image.open(png_path)
                width, height = image.size
                tree = ET.parse(xml_path)
                root_xml = tree.getroot()
                elements = root_xml.find('Elements')
                for elem in elements:
                    icon_name = elem.attrib["name"].lower()
                    if icon_name == name:
                        output_name = f"{name.replace('.tex', '')}.png"
                        output_file = os.path.join(output_dir, output_name)
                        if skip_output and os.path.exists(output_file):
                            progress_lines.append(f"{output_name} - skipped (already exists)")
                            found = True
                            found_any = True
                            break
                        if force64:
                            u1 = float(elem.attrib["u1"])
                            u2 = float(elem.attrib["u2"])
                            v1 = float(elem.attrib["v1"])
                            v2 = float(elem.attrib["v2"])
                            center_x = int(((u1 + u2) / 2) * width)
                            center_y = int(((2 - v1 - v2) / 2) * height)
                            half = 32
                            left = max(center_x - half, 0)
                            top = max(center_y - half, 0)
                            right = min(center_x + half, width)
                            bottom = min(center_y + half, height)
                        else:
                            u1 = float(elem.attrib["u1"])
                            u2 = float(elem.attrib["u2"])
                            v1 = float(elem.attrib["v1"])
                            v2 = float(elem.attrib["v2"])
                            left = int(u1 * width)
                            right = int(u2 * width)
                            top = int((1 - v2) * height)
                            bottom = int((1 - v1) * height)
                        cropped = image.crop((left, top, right, bottom))
                        os.makedirs(output_dir, exist_ok=True)
                        cropped.save(output_file)
                        found = True
                        found_any = True
                        progress_lines.append(f"{output_name} - success!")
                        self.status_label.config(text="Cropping...", fg="blue")
                        self.progress_label.config(text="\n".join(progress_lines))
                        break
                if found:
                    break
            if not found:
                progress_lines.append(f"{name.replace('.tex', '')} - file not found")
                self.progress_label.config(text="\n".join(progress_lines))
            done_names.add(name)
        if found_any:
            self.status_label.config(text="Cropping completed.", fg="green")
        else:
            self.status_label.config(text="No icons found.", fg="red")
        self.icon_names_text.delete("1.0", tk.END)

# Focus management for restoring focus on tab switch, and clear selection on tab change
last_focus_widget = [None]
def on_tab_changed(event):
    notebook = event.widget
    # Save currently focused widget
    if last_focus_widget[0] is not None:
        try:
            last_focus_widget[0].selection_clear()
        except Exception:
            pass
    last_focus_widget[0] = notebook.focus_get()
    # Restore focus after tab change, and clear selection
    def restore_focus():
        if last_focus_widget[0]:
            try:
                last_focus_widget[0].focus_set()
                if isinstance(last_focus_widget[0], tk.Entry):
                    last_focus_widget[0].selection_clear()
            except Exception:
                pass
    notebook.after(10, restore_focus)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("KTools - Multi Converter")
    root.geometry("700x400")
    root.minsize(600, 350)
    root.option_add("*Font", "Arial 12")
    style = ttk.Style()
    style.configure('TNotebook.Tab', font=('Arial', 12))
    notebook = ttk.Notebook(root)
    notebook.pack(fill='both', expand=True)
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    frame_ktech = tk.Frame(notebook)
    notebook.add(frame_ktech, text="ktech")
    ktech_tab = KtechTab(frame_ktech, config)
    frame_krane = tk.Frame(notebook)
    notebook.add(frame_krane, text="krane")
    KraneTab(frame_krane, config, ktech_tab)
    frame_crop = tk.Frame(notebook)
    notebook.add(frame_crop, text="Crop")
    CropTab(frame_crop, config)
    notebook.bind('<<NotebookTabChanged>>', on_tab_changed)
    root.mainloop()

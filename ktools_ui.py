import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
from subprocess import DEVNULL
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
        self.parent.grid_columnconfigure(0, weight=0, minsize=90)
        self.parent.grid_columnconfigure(1, weight=1, minsize=120)
        self.parent.grid_columnconfigure(2, weight=0, minsize=80)
        self.parent.grid_rowconfigure(0, minsize=38)
        self.parent.grid_rowconfigure(1, minsize=38)

    def setup_common_ui(self, row, title_text, button_text, browse_command, browse, button_command, cancel_command, force64_option=False):
        # Select input files row
        self.setup_input_ui(row, title_text, browse_command, browse)

        # skip, convert, cancel row
        self.setup_skip_convert_ui(row+1, button_text, button_command, cancel_command, force64_option)

        # status row
        self.setup_status_ui(row+2)

    def setup_input_ui(self, row, title, command, browse=True):
        tk.Label(self.parent, text=title).grid(row=row, column=0, sticky='ne', padx=2, pady=5)

        text_frame = tk.Frame(self.parent)
        text_frame.grid(row=row, column=1, sticky='nsew', padx=3, pady=5)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.input_text = tk.Text(text_frame, height=7, wrap='word')
        self.input_text.grid(row=0, column=0, sticky='nsew')

        self.scrollbar = AutoScrollbar(text_frame, orient="vertical", command=self.input_text.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.input_text['yscrollcommand'] = self.scrollbar.set

        if not browse:
            return
        tk.Button(self.parent, text="Browse", command=command).grid(row=row, column=2, padx=5, pady=5, sticky='n')

    def setup_skip_convert_ui(self, row, text, command, cancel_command, force64_option=False):
        # Skip, Convert/Crop, Cancel
        self.skip_var = tk.IntVar(value=0)
        action_frame = tk.Frame(self.parent)
        action_frame.grid(row=row, column=1, sticky='we', pady=5)
        action_frame.grid_columnconfigure(0, weight=1)
        inner_row = 0

        # Only appear at Crop tab
        if force64_option:
            self.force64_var = tk.IntVar(value=0)
            self.force64_checkbox = tk.Checkbutton(action_frame, text="Force 64px crop", variable=self.force64_var)
            self.force64_checkbox.grid(row=inner_row, column=0, sticky="w")
            inner_row = inner_row + 1

        self.skip_checkbox = tk.Checkbutton(
            action_frame, text="Skip if output files exist",
            variable=self.skip_var
        )
        self.skip_checkbox.grid(row=inner_row, column=0, sticky="w")

        self.convert_btn = tk.Button(action_frame, text=text, command=command)
        self.convert_btn.grid(row=inner_row, column=1, sticky="e", padx=5)
        self.cancel_btn = tk.Button(action_frame, text="Cancel", command=cancel_command, state="disabled")
        self.cancel_btn.grid(row=inner_row, column=2, sticky="e", padx=5)

    def setup_status_ui(self, row):
        self.status_frame = tk.Frame(self.parent)
        self.status_frame.grid(row=row, column=1, columnspan=2, sticky='nsew', pady=(5, 0))

        self.status_label = tk.Label(self.status_frame, text="", fg="green")
        self.status_label.pack(side='top', anchor='w')

        self.skipped_label = tk.Label(self.status_frame, text="", fg="gray")
        self.skipped_label.pack(side='top', anchor='w')
        pass

    def show_error(self, msg):
        self.parent.after(0, lambda: self.status_label.config(text=msg, fg="red"))
        self.parent.after(0, lambda: self.set_converting_state(False))

    def set_converting_state(self, is_converting: bool):
        if is_converting:
            self.convert_btn.config(state="disabled")
            self.cancel_btn.config(state="normal")
        else:
            self.convert_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

class KtechTab(BaseTab):
    def __init__(self, parent, config):
        super().__init__(parent, config)
        last_ktech = self.config.get("folders", KTECH_SOURCE, fallback="")
        last_output = self.config.get("folders", KTECH_OUTPUT, fallback="")

        self.ktech_dir_var = tk.StringVar(value=last_ktech)
        self.ktech_selector = FileFolderSelector(
            parent, "ktech folder", self.ktech_dir_var, config=self.config, key=KTECH_SOURCE, row=0
        )

        self.output_dir_var = tk.StringVar(value=last_output)
        self.output_selector = FileFolderSelector(
            parent, "Output folder", self.output_dir_var, config=self.config, key=KTECH_OUTPUT, row=1
        )

        self.setup_common_ui(
            2, "Tex files", "Convert", self.select_tex_files, 
            True, self.start_convert, self.cancel_convert
        )
        self.tex_files = []
        
        self._convert_thread = None
        self._cancel_flag = False
        self._current_proc = None

    def select_tex_files(self):
        paths = filedialog.askopenfilenames(
            title="Select .tex files to convert",
            filetypes=[("Klei TEX files", "*.tex")])
        if paths:
            self.tex_files = list(paths)
            self.input_text.config(state='normal')
            self.input_text.delete("1.0", tk.END)
            for p in self.tex_files:
                self.input_text.insert(tk.END, os.path.basename(p) + "\n")
            self.input_text.config(state='disabled')

    def start_convert(self):
        self.status_label.config(text="Converting...", fg="blue")
        self.skipped_label.config(text="")
        self.set_converting_state(True)
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
        self.set_converting_state(False)

    def update_progress(self, idx, text):
        self.input_text.config(state='normal')
        self.input_text.delete(f"{idx+1}.0", f"{idx+1}.end")
        self.input_text.insert(f"{idx+1}.0", text)
        self.input_text.config(state='disabled')

    def convert(self):
        ktech_dir = self.ktech_dir_var.get()
        output_dir = self.output_dir_var.get()
        skip_existing = self.skip_var.get()
        if not output_dir:
            self.show_error("Please select output folder.")
            return
        if not self.tex_files:
            self.show_error("Please select tex files to convert.")
            self.input_text.config(state='normal')
            self.input_text.delete("1.0", tk.END)
            self.input_text.config(state='disabled')
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
            line = f"{base}.tex - Converting..."
            self.parent.after(0, lambda i=idx, l=line: self.update_progress(i, l))
            if skip_existing and os.path.exists(out_png):
                skipped += 1
                line = f"{base}.tex - Skipped"
                self.parent.after(0, lambda i=idx, l=line: self.update_progress(i, l))
                continue
            cmd = f'"{ktech_exe}" "{tex_file}" "{output_dir}"'
            try:
                self._current_proc = subprocess.Popen(cmd, shell=True, stdout=DEVNULL)
                self._current_proc.wait()
                if self._current_proc.returncode != 0:
                    errors.append(base + ".tex")
                    line = f"{base}.tex - Failed!"
                else:
                    line = f"{base}.tex - Success!"
            except Exception:
                errors.append(base + ".tex")
                line = f"{base}.tex - Failed!"
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
        self.parent.after(0, lambda: self.set_converting_state(False))

    def clear_inputs(self):
        self.tex_files = []

class KraneTab(BaseTab):
    def __init__(self, parent, config, ktech_tab_ref):
        super().__init__(parent, config)
        self.parent = parent
        self.config = config
        self.ktech_tab_ref = ktech_tab_ref
        last_krane = self.config.get("folders", KRANE_SOURCE, fallback=ktech_tab_ref.ktech_dir_var.get() if ktech_tab_ref else "")

        self.krane_dir_var = tk.StringVar(value=last_krane)
        self.krane_selector = FileFolderSelector(
            parent, "krane folder", self.krane_dir_var, config=self.config, key=KRANE_SOURCE, row=0
        )

        self.setup_common_ui(
            1, "Anim folders", "Convert", self.select_anim_folder, 
            True, self.start_convert, self.cancel_convert
        )
        self.anim_folders = []

        self._convert_thread = None
        self._cancel_flag = False
        self._current_proc = None

    def select_anim_folder(self):
        # path = os.path.basename(filedialog.askdirectory(title="Select an anim folder"))
        path = filedialog.askdirectory(title="Select an anim folder")
        if path and path not in self.anim_folders:
            self.anim_folders.append(path)
            self.input_text.config(state='normal')
            self.input_text.delete("1.0", tk.END)
            for folder in self.anim_folders:
                self.input_text.insert(tk.END, os.path.basename(folder) + "\n")
            self.input_text.config(state='disabled')

    def start_convert(self):
        self.status_label.config(text="Converting...", fg="blue")
        self.skipped_label.config(text="")
        self.set_converting_state(True)
        self._cancel_flag = False
        self._convert_thread = threading.Thread(target=self.convert)
        self._convert_thread.start()

    def update_folder_status(self, idx, text):
        self.input_text.config(state='normal')
        line_content = self.input_text.get(f"{idx+1}.0", f"{idx+1}.end")
        if line_content.strip(): 
            self.input_text.delete(f"{idx+1}.0", f"{idx+1}.end")
            self.input_text.insert(f"{idx+1}.0", text)
        self.input_text.config(state='disabled')

    def cancel_convert(self):
        self._cancel_flag = True
        if self._current_proc is not None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self.status_label.config(text="Conversion cancelled.", fg="red")
        self.set_converting_state(False)

    def convert(self):
        krane_dir = self.krane_dir_var.get()
        skip_existing = self.skip_var.get()
        
        if not self.anim_folders:
            self.show_error("Please select anim folders.")
            self.input_text.config(state='normal')
            self.input_text.delete("1.0", tk.END)
            self.input_text.config(state='disabled')
            return
        if krane_dir:
            krane_exe = os.path.join(krane_dir, "krane")
            if os.name == 'nt':
                krane_exe += ".exe"
        else:
            krane_exe = "krane"
        errors = []
        skipped = 0
        for idx, folder in enumerate(self.anim_folders):
            if self._cancel_flag:
                break
            base_name = os.path.basename(folder)
            output_dir = os.path.join(folder, "output")
            os.makedirs(output_dir, exist_ok=True)

            line = f"{base_name} - Converting..."
            self.parent.after(0, lambda i=idx, l=line: self.update_folder_status(i, l))
            if skip_existing and any(f.endswith(".scml") for f in os.listdir(output_dir)):
                skipped += 1
                line = f"{base_name} - Skipped"
                self.parent.after(0, lambda i=idx, l=line: self.update_folder_status(i, l))
                continue
            cmd = f'"{krane_exe}" "{folder}" "{output_dir}"'
            try:
                self._current_proc = subprocess.Popen(cmd, shell=True, stdout=DEVNULL)
                self._current_proc.wait()
                if self._current_proc.returncode != 0:
                    errors.append(base_name)
                    line = f"{base_name} - Failed!"
                else:
                    line = f"{base_name} - Success!"
            except Exception:
                errors.append(base_name)
                line = f"{base_name} - Failed!"
            finally:
                self._current_proc = None
            self.parent.after(0, lambda i=idx, l=line: self.update_folder_status(i, l))
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
        self.parent.after(0, lambda: self.set_converting_state(False))

    def clear_inputs(self):
        self.anim_folders = []

class CropTab(BaseTab):
    def __init__(self, parent, config):
        super().__init__(parent, config)
        self.parent = parent
        self.config = config
        last_source = self.config.get("folders", CROP_SOURCE, fallback="")
        last_output = self.config.get("folders", CROP_OUTPUT, fallback="")

        self.source_dir_var = tk.StringVar(value=last_source)
        self.source_selector = FileFolderSelector(
            parent, "Image folder", self.source_dir_var, config=self.config, key=CROP_SOURCE, row=0
        )

        self.output_dir_var = tk.StringVar(value=last_output)
        self.output_selector = FileFolderSelector(
            parent, "Output folder", self.output_dir_var, config=self.config, key=CROP_OUTPUT, row=1
        )

        self.setup_common_ui(
            2, "Icon names", "Crop", None, False, self.start_crop, self.cancel_crop, force64_option=True
        )

    def start_crop(self):
        self.status_label.config(text="Cropping...", fg="blue")
        self.skipped_label.config(text="")
        self.set_converting_state(True)
        self._cancel_flag = False
        self._crop_thread = threading.Thread(target=self.crop_icons)
        self._crop_thread.start()

    def cancel_crop(self):
        self._cancel_flag = True
        self.status_label.config(text="Cropping cancelled.", fg="red")
        self.set_converting_state(False)
        
    def update_progress(self, idx, text):
        self.input_text.delete(f"{idx+1}.0", f"{idx+1}.end")
        self.input_text.insert(f"{idx+1}.0", text)

    def crop_icons(self):
        source_dir = self.source_dir_var.get()
        output_dir = self.output_dir_var.get()
        icon_names = self.input_text.get("1.0", tk.END).strip().splitlines()
        force64 = self.force64_var.get() == 1
        skip_output = self.skip_var.get() == 1

        if not source_dir:
            self.show_error("Please select source folder.")
            return
        if not output_dir:
            self.show_error("Please select output folder.")
            return
        if not icon_names:
            self.show_error("Please enter icon names.")
            return

        xml_files = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.endswith(".xml")]
        if not xml_files:
            self.show_error("No XML files found in source folder.")
            return

        names = [
            n.strip().lower().replace(".tex", "") + ".tex"
            for n in icon_names 
            if n.strip()
        ]

        skipped = 0
        done_names = set()
        for idx, name in enumerate(names):
            if self._cancel_flag:
                self.parent.after(0, lambda: self.status_label.config(text="Cropping cancelled.", fg="red"))
                break
            if name in done_names:
                continue
            found = False
            for xml_path in xml_files:
                png_path = os.path.splitext(xml_path)[0] + ".png"
                if not os.path.exists(png_path):
                    continue  # No png file, skip
                image = Image.open(png_path)
                width, height = image.size
                tree = ET.parse(xml_path)
                root_xml = tree.getroot()
                elements = root_xml.find('Elements')
                for elem in elements:
                    icon_name = elem.attrib["name"].lower()
                    if icon_name == name:
                        base_name = os.path.splitext(name)[0]
                        output_file = os.path.join(output_dir, base_name + ".png")
                        if skip_output and os.path.exists(output_file):
                            line = f"{base_name} - Skipped"
                            found = True
                            skipped += 1
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
                        line = f"{base_name} - Success!"
                        found = True
                        break
                if found:
                    break
            if not found:
                line = f"{name.replace('.tex', '')} - File not found"
            self.parent.after(0, lambda i=idx, l=line: self.update_progress(i, l))
            done_names.add(name)
        if self._cancel_flag:
            self.parent.after(0, lambda: self.status_label.config(text="Cropping cancelled.", fg="red"))
        else:
            self.parent.after(0, lambda: self.status_label.config(text="Cropping completed.", fg="green"))
            
        if skipped > 0:
            self.parent.after(0, lambda: self.skipped_label.config(
                text=f"Skipped {skipped} file(s) because already exists."))
        else:
            self.parent.after(0, lambda: self.skipped_label.config(text=""))

        self.parent.after(0, lambda: self.set_converting_state(False))

# Focus management for restoring focus on tab switch, and clear selection on tab change
last_focus_widget = [None]
def on_tab_changed(event):
    notebook = event.widget
    last_focus_widget[0] = notebook.focus_get()
    # Restore focus after tab change, and clear selection
    def restore_focus():
        widget = last_focus_widget[0]
        if widget and widget.winfo_exists() and widget.winfo_ismapped():
            widget.focus_set()
            if isinstance(widget, (tk.Entry, tk.Text)):
                try:
                    widget.selection_clear()
                except Exception:
                    pass
        else:
            notebook.after(30, restore_focus)
    notebook.after(30, restore_focus)

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

"""Simple Tkinter GUI for running CSV → STDF conversions with batch support."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import List

from csv_to_stdf import convert_csv_file, load_meta_config


class ConverterGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CSV → STDF Converter")
        self.files: List[Path] = []
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_layout()
        self.root.after(150, self._drain_log_queue)

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # File selection section
        file_label = ttk.Label(main, text="CSV Files")
        file_label.grid(row=0, column=0, sticky="w")

        self.file_listbox = tk.Listbox(main, height=8, selectmode=tk.EXTENDED)
        self.file_listbox.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(4, 8))
        file_scroll = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.file_listbox.yview)
        file_scroll.grid(row=1, column=3, sticky="nsw", pady=(4, 8))
        self.file_listbox.config(yscrollcommand=file_scroll.set)

        button_frame = ttk.Frame(main)
        button_frame.grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 12))
        ttk.Button(button_frame, text="Add CSV Files", command=self._add_files).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(button_frame, text="Remove Selected", command=self._remove_selected).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(button_frame, text="Clear All", command=self._clear_files).grid(row=0, column=2)

        # Output directory selector
        self.output_dir_var = tk.StringVar(value=str(Path.cwd()))
        ttk.Label(main, text="Output Directory").grid(row=3, column=0, sticky="w")
        output_entry = ttk.Entry(main, textvariable=self.output_dir_var)
        output_entry.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        ttk.Button(main, text="Browse", command=self._browse_output_dir).grid(row=4, column=3, sticky="ew", padx=(6, 0))

        # Metadata file selector
        self.meta_file_var = tk.StringVar()
        ttk.Label(main, text="Metadata JSON (optional)").grid(row=5, column=0, sticky="w")
        meta_entry = ttk.Entry(main, textvariable=self.meta_file_var)
        meta_entry.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        ttk.Button(main, text="Browse", command=self._browse_meta_file).grid(row=6, column=3, sticky="ew", padx=(6, 0))

        # Head/Site controls
        head_site_frame = ttk.Frame(main)
        head_site_frame.grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 8))
        self.head_var = tk.StringVar(value="1")
        self.site_var = tk.StringVar(value="1")
        ttk.Label(head_site_frame, text="Head #").grid(row=0, column=0, sticky="w")
        ttk.Entry(head_site_frame, width=6, textvariable=self.head_var).grid(row=0, column=1, padx=(4, 16))
        ttk.Label(head_site_frame, text="Site #").grid(row=0, column=2, sticky="w")
        ttk.Entry(head_site_frame, width=6, textvariable=self.site_var).grid(row=0, column=3, padx=(4, 0))

        # Action buttons
        action_frame = ttk.Frame(main)
        action_frame.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(8, 8))
        self.run_button = ttk.Button(action_frame, text="Convert", command=self._start_conversion)
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_frame, text="Quit", command=self.root.destroy).grid(row=0, column=1)

        # Log output
        ttk.Label(main, text="Activity Log").grid(row=9, column=0, sticky="w")
        self.log_text = tk.Text(main, height=10, state=tk.DISABLED)
        self.log_text.grid(row=10, column=0, columnspan=4, sticky="nsew", pady=(4, 0))

        for col in range(4):
            main.columnconfigure(col, weight=1)
        main.rowconfigure(10, weight=1)

    def _add_files(self) -> None:
        selections = filedialog.askopenfilenames(
            title="Select CSV files",
            filetypes=(("CSV Files", "*.csv"), ("All Files", "*.*")),
        )
        for path in selections:
            candidate = Path(path)
            if candidate not in self.files:
                self.files.append(candidate)
                self.file_listbox.insert(tk.END, str(candidate))

    def _remove_selected(self) -> None:
        selected_indices = list(self.file_listbox.curselection())
        for index in reversed(selected_indices):
            self.file_listbox.delete(index)
            del self.files[index]

    def _clear_files(self) -> None:
        self.file_listbox.delete(0, tk.END)
        self.files.clear()

    def _browse_output_dir(self) -> None:
        directory = filedialog.askdirectory(title="Select output directory")
        if directory:
            self.output_dir_var.set(directory)

    def _browse_meta_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select metadata JSON",
            filetypes=(("JSON", "*.json"), ("All Files", "*.*")),
        )
        if file_path:
            self.meta_file_var.set(file_path)

    def _start_conversion(self) -> None:
        if not self.files:
            messagebox.showwarning("No files", "Please add at least one CSV file.")
            return

        try:
            head = int(self.head_var.get())
        except ValueError:
            head = 1
        try:
            site = int(self.site_var.get())
        except ValueError:
            site = 1

        output_dir = Path(self.output_dir_var.get()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        meta_file = self.meta_file_var.get().strip() or None

        self.run_button.config(state=tk.DISABLED)
        self._log("Starting conversion…")
        thread = threading.Thread(
            target=self._run_conversion_thread,
            args=(list(self.files), output_dir, meta_file, head, site),
            daemon=True,
        )
        thread.start()

    def _run_conversion_thread(
        self,
        files: List[Path],
        output_dir: Path,
        meta_file: str | None,
        head: int,
        site: int,
    ) -> None:
        try:
            meta_cfg = load_meta_config(meta_file, default_head=head, default_site=site)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Failed to load metadata: {exc}")
            self._notify_complete()
            return

        failures = 0
        for csv_path in files:
            output_path = output_dir / f"{csv_path.stem}.stdf"
            try:
                convert_csv_file(csv_path, output_path, meta_cfg, source_label="GUI")
                self._log(f"✔ Converted {csv_path} → {output_path}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                self._log(f"✖ Failed {csv_path}: {exc}")

        summary = "Conversion finished with no errors." if failures == 0 else f"Conversion finished with {failures} error(s)."
        self._log(summary)
        self._notify_complete()

    def _notify_complete(self) -> None:
        self.root.after(0, lambda: self.run_button.config(state=tk.NORMAL))

    def _log(self, message: str) -> None:
        self.log_queue.put(message)

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(150, self._drain_log_queue)


def main() -> None:
    root = tk.Tk()
    ConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

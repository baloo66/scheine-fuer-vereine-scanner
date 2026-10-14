#!/usr/bin/env python3
"""QR-Code-Scanner für den Brother DCP-J725DW (Flachbett).

Auf Knopfdruck (Button oder Enter-Taste) wird eine A4-Seite vom Auflageglas
eingelesen, alle QR-Codes darauf werden erkannt und neue Codes an eine
Textdatei angehängt (ein Code pro Zeile). Codes, die schon in der Datei
stehen, werden als Duplikat gemeldet und nicht erneut geschrieben.

Benötigt: scanimage (sane-utils, brscan4) sowie die Python-Pakete
zxing-cpp und pillow (siehe start.sh).
"""

import datetime
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import zxingcpp
from PIL import Image

DEVICE = "brother4:net1;dev0"
RESOLUTION = 300  # dpi – reicht für QR-Codes, höher = langsamer
SCAN_TIMEOUT = 180  # Sekunden

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(APP_DIR, "qr-codes.txt")
SCAN_DIR = os.path.join(APP_DIR, "scans")


def scan_page(png_path):
    """Liest eine A4-Seite vom Flachbett als PNG ein."""
    cmd = [
        "scanimage", "-d", DEVICE,
        "--source", "FlatBed",
        "--mode", "True Gray",
        "--resolution", str(RESOLUTION),
        "-l", "0", "-t", "0", "-x", "210", "-y", "297",
        "--format=png", "-o", png_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=SCAN_TIMEOUT)
    if res.returncode != 0 or not os.path.exists(png_path):
        raise RuntimeError(f"Scan fehlgeschlagen:\n{res.stderr.strip()}")


def decode_qr(png_path):
    """Gibt alle QR-Code-Inhalte des Bildes in Lesereihenfolge zurück."""
    with Image.open(png_path) as img:
        results = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
    codes = []
    for r in results:
        # Mehrzeilige Inhalte auf eine Zeile bringen (ein Code pro Zeile in der Datei)
        text = " ".join(r.text.split())
        if not text:
            continue
        pts = [r.position.top_left, r.position.top_right,
               r.position.bottom_left, r.position.bottom_right]
        codes.append((min(p.y for p in pts), min(p.x for p in pts), text))
    # Zeilenweise sortieren: oben→unten, links→rechts (Toleranz ~1 cm)
    band = RESOLUTION / 2.54
    codes.sort(key=lambda c: (int(c[0] // band), c[1]))
    return [c[2] for c in codes]


class App:
    def __init__(self, root):
        self.root = root
        self.output = DEFAULT_OUTPUT
        self.known = set()
        self.page = 0
        self.busy = False
        self.events = queue.Queue()

        root.title("QR-Scanner – Brother DCP-J725DW")
        root.geometry("760x520")

        top = tk.Frame(root, padx=10, pady=10)
        top.pack(fill="x")
        self.btn = tk.Button(top, text="Seite scannen  (Enter)", font=("Sans", 14, "bold"),
                             bg="#2e7d32", fg="white", activebackground="#388e3c",
                             padx=20, pady=10, command=self.start_scan)
        self.btn.pack(side="left")
        self.status = tk.Label(top, text="Bereit – Seite auflegen und scannen.",
                               font=("Sans", 11), anchor="w", padx=15)
        self.status.pack(side="left", fill="x", expand=True)

        file_row = tk.Frame(root, padx=10)
        file_row.pack(fill="x")
        tk.Label(file_row, text="Ausgabedatei:").pack(side="left")
        self.file_lbl = tk.Label(file_row, anchor="w", fg="#1565c0")
        self.file_lbl.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(file_row, text="Ändern …", command=self.choose_file).pack(side="right")

        opt_row = tk.Frame(root, padx=10)
        opt_row.pack(fill="x")
        self.keep_scans = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_row, text=f"Scan-Bilder speichern (in {SCAN_DIR})",
                       variable=self.keep_scans).pack(side="left")
        self.count_lbl = tk.Label(opt_row, font=("Sans", 11, "bold"))
        self.count_lbl.pack(side="right")

        self.log = scrolledtext.ScrolledText(root, font=("Monospace", 10), state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=10)
        self.log.tag_config("new", foreground="#2e7d32")
        self.log.tag_config("dup", foreground="#e65100")
        self.log.tag_config("err", foreground="#c62828")
        self.log.tag_config("head", font=("Monospace", 10, "bold"))

        root.bind("<Return>", lambda e: self.start_scan())
        root.bind("<KP_Enter>", lambda e: self.start_scan())

        self.load_known()
        self.root.after(100, self.poll_events)

    # ---------- Datei ----------
    def load_known(self):
        self.known = set()
        if os.path.exists(self.output):
            with open(self.output, encoding="utf-8") as f:
                self.known = {line.strip() for line in f if line.strip()}
        self.file_lbl.config(text=self.output)
        self.update_count()
        self.write_log(f"Ausgabedatei: {self.output} ({len(self.known)} Codes vorhanden)\n", "head")

    def choose_file(self):
        if self.busy:
            return
        path = filedialog.asksaveasfilename(
            title="Ausgabedatei wählen", initialfile=os.path.basename(self.output),
            initialdir=os.path.dirname(self.output), defaultextension=".txt",
            confirmoverwrite=False, filetypes=[("Textdatei", "*.txt"), ("Alle", "*")])
        if path:
            self.output = path
            self.load_known()

    def update_count(self):
        self.count_lbl.config(text=f"Codes in Datei: {len(self.known)}")

    # ---------- Scan ----------
    def start_scan(self):
        if self.busy:
            return
        self.busy = True
        self.page += 1
        self.btn.config(state="disabled", bg="#9e9e9e")
        self.status.config(text=f"Scanne Seite {self.page} … (ca. 15 s)")
        threading.Thread(target=self.worker, args=(self.page, self.keep_scans.get()),
                         daemon=True).start()

    def worker(self, page, keep):
        tmpdir = tempfile.mkdtemp(prefix="qrscan-")
        png = os.path.join(tmpdir, "page.png")
        try:
            scan_page(png)
            self.events.put(("status", f"Seite {page} gescannt – erkenne QR-Codes …"))
            codes = decode_qr(png)
            if keep:
                os.makedirs(SCAN_DIR, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy(png, os.path.join(SCAN_DIR, f"seite-{stamp}.png"))
            self.events.put(("result", page, codes))
        except Exception as e:  # noqa: BLE001 – Fehler in der GUI anzeigen
            self.events.put(("error", page, str(e)))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "status":
                    self.status.config(text=ev[1])
                elif ev[0] == "result":
                    self.handle_result(ev[1], ev[2])
                    self.finish()
                elif ev[0] == "error":
                    self.write_log(f"Seite {ev[1]}: FEHLER – {ev[2]}\n", "err")
                    self.status.config(text="Fehler beim Scannen – siehe Protokoll.")
                    self.finish()
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def finish(self):
        self.busy = False
        self.btn.config(state="normal", bg="#2e7d32")

    def handle_result(self, page, codes):
        new, dups = [], []
        for c in codes:
            if c in self.known or c in new:
                dups.append(c)
            else:
                new.append(c)
        if new:
            try:
                with open(self.output, "a", encoding="utf-8") as f:
                    f.writelines(c + "\n" for c in new)
            except OSError as e:
                messagebox.showerror("Schreibfehler", str(e))
                return
            self.known.update(new)

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.write_log(f"\n[{ts}] Seite {page}: {len(codes)} QR-Codes erkannt, "
                       f"{len(new)} neu, {len(dups)} doppelt\n", "head")
        for c in new:
            self.write_log(f"  + {c}\n", "new")
        for c in dups:
            self.write_log(f"  = {c}  (bereits vorhanden)\n", "dup")
        if not codes:
            self.write_log("  Keine QR-Codes gefunden – liegt die Seite richtig?\n", "err")
        self.update_count()
        self.status.config(text=f"Seite {page} fertig: {len(new)} neue Codes. "
                                f"Nächste Seite auflegen und Enter drücken.")
        self.root.bell()

    def write_log(self, text, tag=None):
        self.log.config(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.config(state="disabled")


def main():
    if not shutil.which("scanimage"):
        sys.exit("'scanimage' nicht gefunden. Bitte installieren: sudo apt install sane-utils")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

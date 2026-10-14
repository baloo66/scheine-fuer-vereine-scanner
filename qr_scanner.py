#!/usr/bin/env python3
"""QR-Code-Scanner für den Brother DCP-J725DW (Flachbett).

Auf Knopfdruck (Button oder Enter-Taste) wird eine A4-Seite vom Auflageglas
eingelesen, alle QR-Codes darauf werden erkannt und neue Codes an eine
Textdatei angehängt (ein Code pro Zeile). Codes, die schon in der Datei
stehen, werden als Duplikat gemeldet und nicht erneut geschrieben.

Alternativ können Bilddateien (z. B. Handyfotos) geöffnet werden; sie werden
genauso ausgewertet. Statt einzelner Bilder kann auch eine Textdatei mit
einer Liste von Dateinamen (eine pro Zeile) oder ein Ordner übergeben werden,
im Fenster über „Bilder öffnen …" oder ohne Fenster auf der Kommandozeile:

    qr_scanner.py [-o AUSGABE.txt] BILD|LISTE.txt|ORDNER ...

Benötigt: scanimage (sane-utils, brscan4) sowie die Python-Pakete
zxing-cpp und pillow (siehe start.sh).
"""

import argparse
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
from PIL import Image, ImageFilter, ImageOps

try:  # optional: HEIC-Fotos (iPhone)
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC = True
except ImportError:
    HEIC = False

DEVICE = "brother4:net1;dev0"
RESOLUTION = 300  # dpi – reicht für QR-Codes, höher = langsamer
SCAN_TIMEOUT = 180  # Sekunden

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(APP_DIR, "qr-codes.txt")
SCAN_DIR = os.path.join(APP_DIR, "scans")
IMAGE_TYPES = "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp" + (" *.heic *.heif" if HEIC else "")
IMAGE_EXTS = {t[1:] for t in IMAGE_TYPES.split()}
LIST_EXTS = {".txt", ".lst"}


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


# Mehrere Erkennungsdurchgänge: (Vorverarbeitung, Skalierung, Binarizer).
# Jeder findet bei schwierigen Bildern (Handyfotos: Schräglage, Unschärfe,
# Rauschen) andere Codes; die Ergebnisse werden anhand der Position vereint.
PASSES = [
    (None, 1.0, None),
    (None, 1.0, zxingcpp.Binarizer.FixedThreshold),
    (None, 1.0, zxingcpp.Binarizer.GlobalHistogram),
    (ImageFilter.UnsharpMask(2, 150, 3), 1.0, None),
    (ImageFilter.MedianFilter(3), 1.0, None),
    (None, 1.5, None),
]


def decode_qr(image_path):
    """Gibt alle QR-Code-Inhalte des Bildes in Lesereihenfolge zurück."""
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)  # Handyfotos: Drehung aus EXIF übernehmen
        img = img.convert("L")
    found = []  # (Mitte x, Mitte y, Größe, Text)
    for filt, scale, binarizer in PASSES:
        im = img.filter(filt) if filt else img
        if scale != 1.0:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        kwargs = {"binarizer": binarizer} if binarizer else {}
        for r in zxingcpp.read_barcodes(im, formats=zxingcpp.BarcodeFormat.QRCode, **kwargs):
            # Mehrzeilige Inhalte auf eine Zeile bringen (ein Code pro Zeile in der Datei)
            text = " ".join(r.text.split())
            if not text:
                continue
            pos = r.position
            pts = [pos.top_left, pos.top_right, pos.bottom_left, pos.bottom_right]
            xs = [p.x / scale for p in pts]
            ys = [p.y / scale for p in pts]
            cx, cy = sum(xs) / 4, sum(ys) / 4
            size = max(max(xs) - min(xs), max(ys) - min(ys), 1)
            # Gleicher Code an gleicher Stelle aus einem anderen Durchgang → überspringen
            if any(t == text and abs(cx - x) < size / 2 and abs(cy - y) < size / 2
                   for x, y, _, t in found):
                continue
            found.append((cx, cy, size, text))
    # Zeilenweise sortieren: oben→unten, links→rechts (Toleranz ~1/30 der Bildhöhe ≈ 1 cm bei A4)
    band = max(img.height / 30, 1)
    found.sort(key=lambda c: (int(c[1] // band), c[0]))
    return [c[3] for c in found]


def expand_paths(args):
    """Löst Bilder, Listendateien (.txt/.lst) und Ordner in eine Bildliste auf.

    Gibt (Bildpfade, Fehlermeldungen) zurück. In Listendateien steht ein
    Dateiname pro Zeile; leere Zeilen und Zeilen mit # werden ignoriert,
    relative Pfade gelten relativ zum Ordner der Listendatei.
    """
    paths, errors = [], []
    for arg in args:
        ext = os.path.splitext(arg)[1].lower()
        if os.path.isdir(arg):
            paths += sorted(os.path.join(arg, f) for f in os.listdir(arg)
                            if os.path.splitext(f)[1].lower() in IMAGE_EXTS)
        elif ext in LIST_EXTS:
            try:
                with open(arg, encoding="utf-8-sig") as f:
                    lines = [line.strip() for line in f]
            except (OSError, UnicodeDecodeError) as e:
                errors.append(f"{arg}: Liste nicht lesbar – {e}")
                continue
            base = os.path.dirname(os.path.abspath(arg))
            paths += [os.path.join(base, os.path.expanduser(line))
                      for line in lines if line and not line.startswith("#")]
        else:
            paths.append(arg)
    return paths, errors


def load_codes(output):
    """Liest die bereits gespeicherten Codes aus der Ausgabedatei."""
    if not os.path.exists(output):
        return set()
    with open(output, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_codes(output, known, codes):
    """Hängt neue Codes an die Datei an und ergänzt known; gibt (neu, doppelt) zurück."""
    new, dups = [], []
    for c in codes:
        if c in known or c in new:
            dups.append(c)
        else:
            new.append(c)
    if new:
        with open(output, "a", encoding="utf-8") as f:
            f.writelines(c + "\n" for c in new)
        known.update(new)
    return new, dups


class App:
    def __init__(self, root, output=DEFAULT_OUTPUT):
        self.root = root
        self.output = output
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
        self.open_btn = tk.Button(top, text="Bilder öffnen …", font=("Sans", 11),
                                  padx=10, pady=10, command=self.open_images)
        self.open_btn.pack(side="left", padx=(10, 0))
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
        self.known = load_codes(self.output)
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

    # ---------- Scan / Bilder ----------
    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.btn.config(state=state, bg="#9e9e9e" if busy else "#2e7d32")
        self.open_btn.config(state=state)

    def start_scan(self):
        if self.busy:
            return
        self.set_busy(True)
        self.page += 1
        self.status.config(text=f"Scanne Seite {self.page} … (ca. 15 s)")
        threading.Thread(target=self.scan_worker, args=(self.page, self.keep_scans.get()),
                         daemon=True).start()

    def open_images(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="Bilder mit QR-Codes öffnen",
            filetypes=[("Bilder und Dateilisten", IMAGE_TYPES + " *.txt *.lst"),
                       ("Bilder", IMAGE_TYPES), ("Dateiliste", "*.txt *.lst"), ("Alle", "*")])
        if not paths:
            return
        paths, errors = expand_paths(paths)
        for err in errors:
            self.write_log(f"\nFEHLER – {err}\n", "err")
        if not paths:
            return
        self.set_busy(True)
        threading.Thread(target=self.image_worker, args=(paths,), daemon=True).start()

    def scan_worker(self, page, keep):
        label = f"Seite {page}"
        tmpdir = tempfile.mkdtemp(prefix="qrscan-")
        png = os.path.join(tmpdir, "page.png")
        try:
            scan_page(png)
            self.events.put(("status", f"{label} gescannt – erkenne QR-Codes …"))
            codes = decode_qr(png)
            if keep:
                os.makedirs(SCAN_DIR, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy(png, os.path.join(SCAN_DIR, f"seite-{stamp}.png"))
            self.events.put(("result", label, codes))
        except Exception as e:  # noqa: BLE001 – Fehler in der GUI anzeigen
            self.events.put(("error", label, str(e)))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.events.put(("done",))

    def image_worker(self, paths):
        for i, path in enumerate(paths, 1):
            label = os.path.basename(path)
            self.events.put(("status", f"Bild {i}/{len(paths)}: {label} – erkenne QR-Codes …"))
            try:
                self.events.put(("result", label, decode_qr(path)))
            except Exception as e:  # noqa: BLE001 – Fehler in der GUI anzeigen
                self.events.put(("error", label, str(e)))
        self.events.put(("done",))

    def poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "status":
                    self.status.config(text=ev[1])
                elif ev[0] == "result":
                    self.handle_result(ev[1], ev[2])
                elif ev[0] == "error":
                    self.write_log(f"\n{ev[1]}: FEHLER – {ev[2]}\n", "err")
                    self.status.config(text="Fehler – siehe Protokoll.")
                elif ev[0] == "done":
                    self.set_busy(False)
                    self.root.bell()
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def handle_result(self, label, codes):
        try:
            new, dups = append_codes(self.output, self.known, codes)
        except OSError as e:
            messagebox.showerror("Schreibfehler", str(e))
            return

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.write_log(f"\n[{ts}] {label}: {len(codes)} QR-Codes erkannt, "
                       f"{len(new)} neu, {len(dups)} doppelt\n", "head")
        for c in new:
            self.write_log(f"  + {c}\n", "new")
        for c in dups:
            self.write_log(f"  = {c}  (bereits vorhanden)\n", "dup")
        if not codes:
            self.write_log("  Keine QR-Codes gefunden – liegt die Seite richtig bzw. ist das Bild scharf?\n", "err")
        self.update_count()
        self.status.config(text=f"{label} fertig: {len(new)} neue Codes. "
                                f"Nächste Seite auflegen und Enter drücken.")

    def write_log(self, text, tag=None):
        self.log.config(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.config(state="disabled")


def run_cli(files, output):
    """Wertet Bilder ohne Fenster aus; Rückgabe 0 = ok, 1 = Fehler aufgetreten."""
    known = load_codes(output)
    paths, errors = expand_paths(files)
    for err in errors:
        print(f"FEHLER – {err}", file=sys.stderr)
    total_new = 0
    for path in paths:
        try:
            codes = decode_qr(path)
            new, dups = append_codes(output, known, codes)
        except Exception as e:  # noqa: BLE001 – pro Datei melden, weitermachen
            print(f"{path}: FEHLER – {e}", file=sys.stderr)
            errors.append(path)
            continue
        total_new += len(new)
        print(f"{path}: {len(codes)} QR-Codes erkannt, {len(new)} neu, {len(dups)} doppelt")
        for c in new:
            print(f"  + {c}")
        for c in dups:
            print(f"  = {c}  (bereits vorhanden)")
    print(f"\n{len(paths)} Bilder, {total_new} neue Codes → {output} ({len(known)} Codes gesamt)")
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(
        description="QR-Codes vom Flachbettscanner oder aus Bildern in eine Textdatei schreiben. "
                    "Ohne Dateien startet das Fenster.")
    parser.add_argument("files", nargs="*", metavar="DATEI",
                        help="Bild, Textdatei mit Dateinamen (.txt/.lst, einer pro Zeile) oder Ordner")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT,
                        help=f"Ausgabedatei (Standard: {DEFAULT_OUTPUT})")
    args = parser.parse_args()
    if args.files:
        sys.exit(run_cli(args.files, args.output))

    if not shutil.which("scanimage"):
        sys.exit("'scanimage' nicht gefunden. Bitte installieren: sudo apt install sane-utils")
    root = tk.Tk()
    App(root, args.output)
    root.mainloop()


if __name__ == "__main__":
    main()

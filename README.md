# Scheine-für-Vereine-Scanner

Liest auf Knopfdruck A4-Seiten vom Auflageglas eines Brother DCP-J725DW ein,
erkennt alle QR-Codes auf jeder Seite und schreibt sie in eine Textdatei,
ein Code pro Zeile. Alternativ lassen sich Bilddateien, z. B. Handyfotos,
auswerten.

## Funktionen

- Scan einer A4-Seite (300 dpi, Graustufen) per Button oder Enter-Taste
- Auswertung von Bilddateien über „Bilder öffnen …" (JPG, PNG, TIFF, BMP,
  WebP, HEIC), mehrere Dateien auf einmal möglich, auch über eine Textdatei
  mit einer Liste von Dateinamen
- Kommandozeilenmodus ohne Fenster für Bilder, Dateilisten und Ordner
- Erkennung mehrerer QR-Codes pro Seite mit [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp)
- Codes werden in Lesereihenfolge (oben nach unten, links nach rechts) an
  `qr-codes.txt` angehängt
- Doppelte Codes werden nicht erneut geschrieben, sondern im Protokoll als
  „bereits vorhanden" gemeldet, auch über mehrere Sitzungen hinweg
- Wahl einer anderen Ausgabedatei über „Ändern …"
- Optional: Speichern der Scan-Bilder im Ordner `scans/`

## Voraussetzungen

- Linux mit Python 3 und Tkinter (`sudo apt install python3-tk python3-venv`)
- SANE und der Brother-Treiber brscan4 (`sudo apt install sane-utils`, brscan4 von der Brother-Website)
- Der Scanner muss für `scanimage -L` als `brother4:net1;dev0` sichtbar sein

## Start

```bash
./start.sh
```

Beim ersten Start legt das Skript eine virtuelle Umgebung in `.venv/` an und
installiert `zxing-cpp`, `pillow` und `pillow-heif` (für iPhone-Fotos im
HEIC-Format). Fehlende Pakete werden bei späteren Starts nachinstalliert.

## Bedienung

1. Seite auf das Glas legen.
2. Auf **„Seite scannen"** klicken oder **Enter** drücken (Dauer ca. 15 s).
3. Ein Ton zeigt an, dass die Seite fertig ist. Nächste Seite auflegen und
   wieder Enter drücken.

Für Fotos: **„Bilder öffnen …"** klicken und eine oder mehrere Bilddateien
auswählen. Sie werden nacheinander ausgewertet, das Ergebnis erscheint pro
Datei im Protokoll.

Statt einzelner Bilder kann auch eine Textdatei (`.txt` oder `.lst`) mit
einer Liste von Dateinamen ausgewählt werden:

```text
# Fotos vom Vereinsfest
IMG_0815.jpg
IMG_0816.heic
/home/ich/Bilder/scan-03.png
```

Ein Dateiname pro Zeile. Leere Zeilen und Zeilen mit `#` werden ignoriert.
Relative Pfade gelten relativ zum Ordner der Listendatei.

Tipps für Handyfotos: Seite möglichst gerade und formatfüllend aufnehmen,
auf Schärfe achten und Spiegelungen (z. B. durch Blitz) vermeiden.

## Kommandozeile (ohne Fenster)

Werden beim Start Dateien übergeben, wertet das Programm sie direkt im
Terminal aus, ohne Fenster und ohne Scanner:

```bash
./start.sh foto1.jpg foto2.heic       # einzelne Bilder
./start.sh liste.txt                  # Textdatei mit Dateinamen
./start.sh ~/Bilder/Vereinsfest/      # alle Bilder eines Ordners
./start.sh -o codes.txt liste.txt     # andere Ausgabedatei
```

Neue Codes werden wie im Fenster an die Ausgabedatei angehängt, Duplikate
gemeldet. Der Rückgabewert ist 1, wenn eine Datei nicht gelesen werden
konnte, sonst 0. Die Option `-o` funktioniert auch beim Start des Fensters.

## Anpassungen

In `qr_scanner.py`:

- `DEVICE`: SANE-Gerätename des Scanners
- `RESOLUTION`: Scan-Auflösung. Bei sehr kleinen QR-Codes auf 600 erhöhen
  (der Scan dauert dann länger).

## Hinweise

- Jedes Bild wird in mehreren Durchgängen mit unterschiedlicher
  Vorverarbeitung ausgewertet. So werden auch Codes auf schrägen, leicht
  unscharfen oder verrauschten Fotos gefunden. Mehrfach gefundene Codes an
  derselben Stelle werden zusammengeführt.
- Enthält ein QR-Code mehrere Zeilen, werden sie mit Leerzeichen zu einer
  Zeile zusammengefügt.
- `qr-codes.txt` und `scans/` stehen in der `.gitignore` und werden nicht
  ins Repository übernommen.

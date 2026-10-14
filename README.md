# Scheine-für-Vereine-Scanner

Liest auf Knopfdruck A4-Seiten vom Auflageglas eines Brother DCP-J725DW ein,
erkennt alle QR-Codes auf jeder Seite und schreibt sie in eine Textdatei,
ein Code pro Zeile.

## Funktionen

- Scan einer A4-Seite (300 dpi, Graustufen) per Button oder Enter-Taste
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
installiert `zxing-cpp` und `pillow`.

## Bedienung

1. Seite auf das Glas legen.
2. Auf **„Seite scannen"** klicken oder **Enter** drücken (Dauer ca. 15 s).
3. Ein Ton zeigt an, dass die Seite fertig ist. Nächste Seite auflegen und
   wieder Enter drücken.

## Anpassungen

In `qr_scanner.py`:

- `DEVICE`: SANE-Gerätename des Scanners
- `RESOLUTION`: Scan-Auflösung. Bei sehr kleinen QR-Codes auf 600 erhöhen
  (der Scan dauert dann länger).

## Hinweise

- Enthält ein QR-Code mehrere Zeilen, werden sie mit Leerzeichen zu einer
  Zeile zusammengefügt.
- `qr-codes.txt` und `scans/` stehen in der `.gitignore` und werden nicht
  ins Repository übernommen.

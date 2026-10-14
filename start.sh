#!/bin/sh
# Startet den QR-Scanner; legt beim ersten Mal die Python-Umgebung an
# bzw. installiert fehlende Pakete nach. Ohne Argumente öffnet sich das
# Fenster, mit Dateien läuft die Auswertung im Terminal (siehe README).
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -x "$DIR/.venv/bin/python" ]; then
    /usr/bin/python3 -m venv --system-site-packages "$DIR/.venv"
fi
if ! "$DIR/.venv/bin/python" -c "import zxingcpp, PIL, pillow_heif" 2>/dev/null; then
    "$DIR/.venv/bin/pip" install -q zxing-cpp pillow pillow-heif
fi
exec "$DIR/.venv/bin/python" "$DIR/qr_scanner.py" "$@"

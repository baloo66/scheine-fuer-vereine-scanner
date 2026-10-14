#!/bin/sh
# Startet den QR-Scanner; legt beim ersten Mal die Python-Umgebung an.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    /usr/bin/python3 -m venv --system-site-packages .venv
    .venv/bin/pip install -q zxing-cpp pillow
fi
exec .venv/bin/python qr_scanner.py "$@"

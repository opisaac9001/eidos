#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Set up Python 3.12 and the virtual environment using README.md first."
    exit 1
fi
# Explicit source path also works if macOS marks editable-install .pth files hidden.
exec .venv/bin/python -c 'import sys; sys.path.insert(0, "src"); from eidos.cli import main; main()' \
    --database "${EIDOS_DATABASE:-data/observatory.sqlite3}" serve "$@"

#!/usr/bin/env sh
set -eu
python3 "$(dirname "$0")/build.py" --root "$(dirname "$0")/.."

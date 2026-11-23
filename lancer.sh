#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi

if ! .venv/bin/python -c "import pygame, streamlit, plotly, pandas, requests, dotenv" 2>/dev/null; then
    .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python interface.py

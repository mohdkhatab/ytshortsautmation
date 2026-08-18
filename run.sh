#!/bin/bash
cd "$(dirname "$0")"

echo "=== Anime Upload Agent ==="
echo "Starting bot..."

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt
else
    source venv/bin/activate
fi

echo "Bot starting..."
python3 main.py

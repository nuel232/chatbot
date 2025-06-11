#!/usr/bin/env bash
# Exit on error
set -e

# Print all commands for debugging
set -x

# Install dependencies
pip install -r requirements.txt

# Ensure app.py exists
if [ ! -f app.py ]; then
  echo "Creating app.py..."
  echo "from main import app, socketio

# This file is just an entry point for Render
# The actual application code is in main.py

if __name__ == \"__main__\":
    socketio.run(app, debug=False)" > app.py
fi

# Ensure the app is ready to run
echo "Build completed successfully" 
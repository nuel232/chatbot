from main import app, socketio

# This file is just an entry point for Render
# The actual application code is in main.py

if __name__ == "__main__":
    socketio.run(app, debug=True) 
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO
from datetime import datetime
import random
import os
import json
import bleach
import markdown
from string import ascii_uppercase

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "hjhjsdahhds")

# Initialize Socket.IO
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)

# In-memory storage for active rooms
rooms = {}

# Helper functions
def process_message_content(content):
    """Process message content - convert markdown to HTML and sanitize"""
    # Convert markdown to HTML
    html = markdown.markdown(content, extensions=['extra', 'nl2br'])
    
    # Define allowed tags and attributes
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'u', 's', 'ul', 'ol', 'li', 
        'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'a', 'hr', 'img'
    ]
    allowed_attrs = {
        '*': ['class'],
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height']
    }
    
    # Sanitize HTML
    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True
    )
    
    return clean_html

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)

        if code not in rooms:
            break

    return code

def get_public_rooms():
    return [{"code": code, "creator": details["creator"]} for code, details in rooms.items() if details["public"]]

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)
        public = request.form.get("public", False)
        
        # Convert string 'true' to boolean True
        is_public = False
        if public == 'true' or public is True:
            is_public = True

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name, public_room_list=get_public_rooms())

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name, public_room_list=get_public_rooms())

        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": [], "public": is_public, "creator": name}
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name, public_room_list=get_public_rooms())

        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html", public_room_list=get_public_rooms())

@app.route("/room")
def room():
    room = session.get("room")
    name = session.get("name")
    
    if room is None or name is None or room not in rooms:
        return redirect(url_for("home"))
    
    return render_template(
        "room.html", 
        code=room, 
        messages=rooms[room]["messages"],
        name=name,
        room_creator=rooms[room]["creator"]
    )

@app.route("/api/message/<int:message_idx>/edit", methods=["POST"])
def edit_message(message_idx):
    if "name" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    room = session.get("room")
    if not room or room not in rooms or message_idx >= len(rooms[room]["messages"]):
        return jsonify({"error": "Message not found"}), 404
    
    message = rooms[room]["messages"][message_idx]
    
    # Only message sender can edit
    if message["name"] != session["name"]:
        return jsonify({"error": "Not authorized"}), 403
    
    data = request.json
    new_content = data.get("content")
    
    if not new_content:
        return jsonify({"error": "Content required"}), 400
    
    # Process the message (markdown, sanitize)
    processed_content = process_message_content(new_content)
    message["raw_content"] = new_content
    message["message"] = processed_content
    message["edited"] = True
    message["edited_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Emit message update to room
    socketio.emit(
        "message_update", 
        {
            "idx": message_idx,
            "message": message["message"],
            "raw_content": message["raw_content"],
            "edited_at": message["edited_at"]
        },
        to=room
    )
    
    return jsonify({"success": True})

@app.route("/api/message/<int:message_idx>/delete", methods=["POST"])
def delete_message(message_idx):
    if "name" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    room = session.get("room")
    if not room or room not in rooms or message_idx >= len(rooms[room]["messages"]):
        return jsonify({"error": "Message not found"}), 404
    
    message = rooms[room]["messages"][message_idx]
    
    # Only message sender or room creator can delete
    if message["name"] != session["name"] and rooms[room]["creator"] != session["name"]:
        return jsonify({"error": "Not authorized"}), 403
    
    # Soft delete
    message["deleted"] = True
    message["message"] = "<em>This message has been deleted.</em>"
    
    # Emit message deletion to room
    socketio.emit(
        "message_delete", 
        {
            "idx": message_idx,
            "deleted": True,
            "message": message["message"]
        },
        to=room
    )
    
    return jsonify({"success": True})

@socketio.on("message")
def message(data):
    room = session.get("room")
    name = session.get("name")
    
    if not room or room not in rooms:
        return
    
    # Process message content (markdown, sanitize)
    raw_content = data["data"]
    processed_content = process_message_content(raw_content)

    # Create message object
    message_obj = {
        "name": name,
        "message": processed_content,
        "raw_content": raw_content,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "edited": False,
        "deleted": False,
        "system_message": False
    }
    
    # Add to room messages
    rooms[room]["messages"].append(message_obj)
    
    # Send to clients
    send(message_obj, to=room)
    print(f"{name} said: {data['data']}")

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return

    join_room(room)
    
    # Create system message
    system_message = {
        "name": name,
        "message": "has entered the room",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "system_message": True
    }
    
    # Add to room messages
    rooms[room]["messages"].append(system_message)
    
    send(system_message, to=room)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    
    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
    
    leave_room(room)
    
    # Create system message
    system_message = {
        "name": name,
        "message": "has left the room",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "system_message": True
    }
    
    # If room still exists, add message
    if room in rooms:
        rooms[room]["messages"].append(system_message)
    
    send(system_message, to=room)
    print(f"{name} has left the room {room}")

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
else:
    # This branch will be used by Gunicorn when deployed
    pass 
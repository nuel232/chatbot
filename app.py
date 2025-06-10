from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random
import os
import json
import bleach
import markdown
from string import ascii_uppercase

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "hjhjsdahhds")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///chat.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
socketio = SocketIO(app)
db = SQLAlchemy(app)

# Database models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(50))
    profile_picture = db.Column(db.String(200), default="default.png")
    settings = db.Column(db.JSON, default=lambda: json.dumps({
        "theme": "light",
        "notifications": True,
        "sounds": True
    }))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='user', lazy=True)
    reactions = db.relationship('Reaction', backref='user', lazy=True)

class Room(db.Model):
    id = db.Column(db.String(4), primary_key=True)
    creator = db.Column(db.String(50), nullable=False)
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='room', lazy=True, cascade="all, delete")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(2000), nullable=False)
    raw_content = db.Column(db.String(2000))  # Store original markdown
    sender = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    room_id = db.Column(db.String(4), db.ForeignKey('room.id'), nullable=False)
    read_by = db.Column(db.JSON, default=lambda: json.dumps([]))
    reactions = db.relationship('Reaction', backref='message', lazy=True, cascade="all, delete")

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emoji = db.Column(db.String(10), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

# In-memory storage for active room members
active_rooms = {}
room_users = {}

# Helper functions
def get_or_create_user(username):
    """Get existing user or create a new one"""
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(
            username=username,
            display_name=username
        )
        db.session.add(user)
        db.session.commit()
    return user

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

        if db.session.get(Room, code) is None:
            break

    return code

def get_public_rooms():
    public_rooms = Room.query.filter_by(is_public=True).all()
    return [{"code": room.id, "creator": room.creator} for room in public_rooms]

def get_user_settings(username):
    user = User.query.filter_by(username=username).first()
    if user:
        return json.loads(user.settings)
    return {
        "theme": "light",
        "notifications": True,
        "sounds": True
    }

def format_message_for_client(message, current_user=None):
    """Format message object for sending to client"""
    # Get reactions grouped by emoji
    reaction_counts = {}
    user_has_reacted = {}
    
    for reaction in message.reactions:
        emoji = reaction.emoji
        if emoji not in reaction_counts:
            reaction_counts[emoji] = 0
            user_has_reacted[emoji] = False
        
        reaction_counts[emoji] += 1
        
        if current_user and reaction.user_id == current_user.id:
            user_has_reacted[emoji] = True
    
    # Format reactions for client
    formatted_reactions = [
        {
            "emoji": emoji,
            "count": count,
            "reacted": user_has_reacted.get(emoji, False)
        }
        for emoji, count in reaction_counts.items()
    ]
    
    # Check if current user has read the message
    is_read = False
    if current_user:
        read_by = json.loads(message.read_by)
        is_read = current_user.username in read_by
    
    return {
        "id": message.id,
        "content": message.content,
        "raw_content": message.raw_content,
        "sender": message.sender,
        "timestamp": message.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "edited_at": message.edited_at.strftime("%Y-%m-%d %H:%M:%S") if message.edited_at else None,
        "is_deleted": message.is_deleted,
        "reactions": formatted_reactions,
        "is_read": is_read
    }

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

        # Get or create user
        user = get_or_create_user(name)

        room = code
        if create != False:
            room = generate_unique_code(4)
            new_room = Room(id=room, creator=name, is_public=is_public)
            db.session.add(new_room)
            db.session.commit()
            active_rooms[room] = {"members": 0}
        elif not db.session.get(Room, room):
            return render_template("home.html", error="Room does not exist.", code=code, name=name, public_room_list=get_public_rooms())

        session["room"] = room
        session["name"] = name
        session["user_id"] = user.id
        return redirect(url_for("room"))

    return render_template("home.html", public_room_list=get_public_rooms())

@app.route("/room")
def room():
    room = session.get("room")
    name = session.get("name")
    user_id = session.get("user_id")
    
    if room is None or name is None:
        return redirect(url_for("home"))
        
    room_data = db.session.get(Room, room)
    if not room_data:
        return redirect(url_for("home"))
    
    # Get user and settings
    user = User.query.get(user_id) if user_id else None
    user_settings = get_user_settings(name)
        
    # Get messages
    messages = Message.query.filter_by(room_id=room).order_by(Message.timestamp).all()
    formatted_messages = [format_message_for_client(msg, user) for msg in messages]
    
    # Mark messages as read for this user
    if user:
        for message in messages:
            if message.sender != name:  # Don't mark own messages
                read_by = json.loads(message.read_by)
                if name not in read_by:
                    read_by.append(name)
                    message.read_by = json.dumps(read_by)
        db.session.commit()
    
    return render_template(
        "room.html", 
        code=room, 
        messages=formatted_messages, 
        room_creator=room_data.creator,
        user=user,
        settings=user_settings
    )

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "name" not in session:
        return redirect(url_for("home"))
    
    user = User.query.filter_by(username=session["name"]).first()
    if not user:
        return redirect(url_for("home"))
    
    if request.method == "POST":
        display_name = request.form.get("display_name")
        profile_picture = request.form.get("profile_picture")
        
        if display_name:
            user.display_name = display_name
            
        if profile_picture:
            user.profile_picture = profile_picture
            
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))
    
    return render_template("profile.html", user=user)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "name" not in session:
        return redirect(url_for("home"))
    
    user = User.query.filter_by(username=session["name"]).first()
    if not user:
        return redirect(url_for("home"))
    
    current_settings = json.loads(user.settings)
    
    if request.method == "POST":
        theme = request.form.get("theme", "light")
        notifications = request.form.get("notifications") == "on"
        sounds = request.form.get("sounds") == "on"
        
        new_settings = {
            "theme": theme,
            "notifications": notifications,
            "sounds": sounds
        }
        
        user.settings = json.dumps(new_settings)
        db.session.commit()
        
        flash("Settings updated successfully!", "success")
        return redirect(url_for("settings"))
    
    return render_template("settings.html", user=user, settings=current_settings)

@app.route("/api/message/<int:message_id>/reaction", methods=["POST"])
def add_reaction(message_id):
    if "name" not in session or "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    message = Message.query.get(message_id)
    if not message:
        return jsonify({"error": "Message not found"}), 404
    
    data = request.json
    emoji = data.get("emoji")
    
    if not emoji:
        return jsonify({"error": "Emoji required"}), 400
    
    # Check if user already reacted with this emoji
    existing_reaction = Reaction.query.filter_by(
        message_id=message_id,
        user_id=session["user_id"],
        emoji=emoji
    ).first()
    
    if existing_reaction:
        # Remove reaction if it exists
        db.session.delete(existing_reaction)
        action = "removed"
    else:
        # Add new reaction
        reaction = Reaction(
            emoji=emoji,
            message_id=message_id,
            user_id=session["user_id"]
        )
        db.session.add(reaction)
        action = "added"
    
    db.session.commit()
    
    # Get updated message with reactions
    updated_message = Message.query.get(message_id)
    user = User.query.get(session["user_id"])
    
    # Emit reaction update to room
    socketio.emit(
        "reaction_update", 
        {
            "message_id": message_id,
            "user": session["name"],
            "emoji": emoji,
            "action": action,
            "message": format_message_for_client(updated_message, user)
        },
        to=message.room_id
    )
    
    return jsonify({"success": True, "action": action})

@app.route("/api/message/<int:message_id>/edit", methods=["POST"])
def edit_message(message_id):
    if "name" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    message = Message.query.get(message_id)
    if not message:
        return jsonify({"error": "Message not found"}), 404
    
    # Only message sender can edit
    if message.sender != session["name"]:
        return jsonify({"error": "Not authorized"}), 403
    
    data = request.json
    new_content = data.get("content")
    
    if not new_content:
        return jsonify({"error": "Content required"}), 400
    
    # Process the message (markdown, sanitize)
    processed_content = process_message_content(new_content)
    message.raw_content = new_content
    message.content = processed_content
    message.edited_at = datetime.utcnow()
    
    db.session.commit()
    
    # Emit message update to room
    socketio.emit(
        "message_update", 
        {
            "id": message.id,
            "content": message.content,
            "raw_content": message.raw_content,
            "edited_at": message.edited_at.strftime("%Y-%m-%d %H:%M:%S")
        },
        to=message.room_id
    )
    
    return jsonify({"success": True})

@app.route("/api/message/<int:message_id>/delete", methods=["POST"])
def delete_message(message_id):
    if "name" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    message = Message.query.get(message_id)
    if not message:
        return jsonify({"error": "Message not found"}), 404
    
    # Only message sender or room creator can delete
    room = Room.query.get(message.room_id)
    if message.sender != session["name"] and room.creator != session["name"]:
        return jsonify({"error": "Not authorized"}), 403
    
    # Soft delete
    message.is_deleted = True
    message.content = "<em>This message has been deleted.</em>"
    
    db.session.commit()
    
    # Emit message deletion to room
    socketio.emit(
        "message_delete", 
        {
            "id": message.id,
            "is_deleted": True,
            "content": message.content
        },
        to=message.room_id
    )
    
    return jsonify({"success": True})

@app.route("/api/message/<int:message_id>/read", methods=["POST"])
def mark_read(message_id):
    if "name" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    message = Message.query.get(message_id)
    if not message:
        return jsonify({"error": "Message not found"}), 404
    
    # Add user to read_by list if not already there
    read_by = json.loads(message.read_by)
    if session["name"] not in read_by:
        read_by.append(session["name"])
        message.read_by = json.dumps(read_by)
        db.session.commit()
        
        # Emit read receipt to room
        socketio.emit(
            "read_receipt", 
            {
                "message_id": message.id,
                "user": session["name"],
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            },
            to=message.room_id
        )
    
    return jsonify({"success": True})

@app.route("/delete/<room_id>", methods=["POST"])
def delete_room(room_id):
    if "name" not in session:
        return redirect(url_for("home"))
        
    room_data = db.session.get(Room, room_id)
    if room_data and room_data.creator == session["name"]:
        db.session.delete(room_data)
        db.session.commit()
        flash("Room deleted successfully!", "success")
    else:
        flash("You don't have permission to delete this room.", "error")
        
    return redirect(url_for("home"))

@socketio.on("message")
def message(data):
    room = session.get("room")
    name = session.get("name")
    user_id = session.get("user_id")
    
    if not room or not db.session.get(Room, room):
        return
    
    # Process message content (markdown, sanitize)
    raw_content = data["data"]
    processed_content = process_message_content(raw_content)

    # Save message to database
    new_message = Message(
        content=processed_content,
        raw_content=raw_content,
        sender=name,
        user_id=user_id,
        room_id=room,
        read_by=json.dumps([name])  # Sender has read their own message
    )
    db.session.add(new_message)
    db.session.commit()
    
    # Get user object for formatting
    user = User.query.get(user_id) if user_id else None
    
    # Format message for clients
    formatted_message = format_message_for_client(new_message, user)
    
    # Add a system_message flag to differentiate from system messages
    formatted_message["system_message"] = False
    
    send(formatted_message, to=room)
    print(f"{name} said: {data['data']}")

@socketio.on("user_join")
def user_join(data):
    room = data.get("room")
    name = data.get("name")
    
    if not room or not name or not db.session.get(Room, room):
        return
        
    if room not in room_users:
        room_users[room] = set()
    
    room_users[room].add(name)
    socketio.emit("user_list", {"users": list(room_users[room])}, to=room)

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    
    if not room or not name:
        return
        
    if not db.session.get(Room, room):
        leave_room(room)
        return

    join_room(room)
    
    if room not in active_rooms:
        active_rooms[room] = {"members": 0}
    
    active_rooms[room]["members"] += 1
    
    if room not in room_users:
        room_users[room] = set()
    
    room_users[room].add(name)
    socketio.emit("user_list", {"users": list(room_users[room])}, to=room)
    
    # Get user data
    user = User.query.filter_by(username=name).first()
    user_data = {
        "name": name,
        "display_name": user.display_name if user else name,
        "profile_picture": user.profile_picture if user else "default.png"
    }
    
    # Create system message
    system_message = {
        "name": name,
        "message": "has entered the room",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "system_message": True,
        "user_data": user_data
    }
    
    send(system_message, to=room)
    print(f"{name} joined room {room}")

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    
    if room in active_rooms:
        active_rooms[room]["members"] -= 1
        if active_rooms[room]["members"] <= 0:
            del active_rooms[room]
    
    if name and room and room in room_users:
        room_users[room].discard(name)
        socketio.emit("user_list", {"users": list(room_users[room])}, to=room)
        
    leave_room(room)
    
    # Create system message
    system_message = {
        "name": name,
        "message": "has left the room",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "system_message": True
    }
    
    send(system_message, to=room)
    print(f"{name} has left the room {room}")

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5001, debug=True) 
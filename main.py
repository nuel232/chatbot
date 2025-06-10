from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random
import os
import json
import re
import hashlib
import bleach
import markdown
from string import ascii_uppercase
from supabase import create_client
import requests
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "hjhjsdahhds")

# Database configuration
# Use PostgreSQL for production, SQLite for development
database_url = os.environ.get("DATABASE_URL")
if database_url:
    # Handle special case for Render's DATABASE_URL format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static/uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size

# Initialize Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase client initialized successfully")
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
else:
    print("Supabase credentials not provided, using local storage only")

# Initialize Socket.IO
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)
db = SQLAlchemy(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

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
    sent_direct_messages = db.relationship('DirectMessage', 
                                         foreign_keys='DirectMessage.sender_id',
                                         backref='sender', 
                                         lazy=True)
    received_direct_messages = db.relationship('DirectMessage', 
                                             foreign_keys='DirectMessage.recipient_id',
                                             backref='recipient', 
                                             lazy=True)

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
    supabase_id = db.Column(db.String(36), nullable=True)  # Store Supabase ID for cloud sync

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emoji = db.Column(db.String(10), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(2000), nullable=False)
    raw_content = db.Column(db.String(2000))  # Store original markdown
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    is_read = db.Column(db.Boolean, default=False)
    supabase_id = db.Column(db.String(36), nullable=True)  # Store Supabase ID for cloud sync

# Create tables
with app.app_context():
    db.create_all()

# Sync data from Supabase if configured
def sync_from_supabase():
    """Synchronize data from Supabase to local database on app startup"""
    if not supabase:
        return
    
    try:
        print("Starting Supabase data synchronization...")
        
        # Sync users
        users_response = supabase.table('users').select('*').execute()
        if users_response.data:
            for user_data in users_response.data:
                # Check if user exists locally
                user = User.query.filter_by(id=user_data.get('id')).first()
                if not user:
                    # Create user locally
                    try:
                        created_at = datetime.fromisoformat(user_data.get('created_at'))
                    except:
                        created_at = datetime.utcnow()
                        
                    user = User(
                        id=user_data.get('id'),
                        username=user_data.get('username'),
                        display_name=user_data.get('display_name'),
                        created_at=created_at
                    )
                    db.session.add(user)
        
        # Sync rooms
        rooms_response = supabase.table('rooms').select('*').execute()
        if rooms_response.data:
            for room_data in rooms_response.data:
                # Check if room exists locally
                room = Room.query.filter_by(id=room_data.get('id')).first()
                if not room:
                    # Create room locally
                    try:
                        created_at = datetime.fromisoformat(room_data.get('created_at'))
                    except:
                        created_at = datetime.utcnow()
                        
                    room = Room(
                        id=room_data.get('id'),
                        creator=room_data.get('creator'),
                        is_public=room_data.get('is_public', False),
                        created_at=created_at
                    )
                    db.session.add(room)
        
        # Sync room messages
        messages_response = supabase.table('messages').select('*').execute()
        if messages_response.data:
            for message_data in messages_response.data:
                # Check if message exists locally by supabase_id
                existing_message = Message.query.filter_by(supabase_id=message_data.get('id')).first()
                if not existing_message:
                    # Check if message exists locally by local_id
                    local_id = message_data.get('local_id')
                    if local_id:
                        existing_message = Message.query.filter_by(id=local_id).first()
                    
                    if not existing_message:
                        # Create message locally
                        try:
                            timestamp = datetime.fromisoformat(message_data.get('timestamp'))
                        except:
                            timestamp = datetime.utcnow()
                            
                        try:
                            edited_at = datetime.fromisoformat(message_data.get('edited_at')) if message_data.get('edited_at') else None
                        except:
                            edited_at = None
                            
                        message = Message(
                            content=message_data.get('content'),
                            raw_content=message_data.get('raw_content'),
                            sender=message_data.get('sender'),
                            user_id=message_data.get('user_id'),
                            timestamp=timestamp,
                            edited_at=edited_at,
                            is_deleted=message_data.get('is_deleted', False),
                            room_id=message_data.get('room_id'),
                            read_by=message_data.get('read_by', json.dumps([])),
                            supabase_id=message_data.get('id')
                        )
                        db.session.add(message)
                    else:
                        # Update existing message with Supabase ID
                        existing_message.supabase_id = message_data.get('id')
        
        # Sync direct messages
        dm_response = supabase.table('direct_messages').select('*').execute()
        if dm_response.data:
            for dm_data in dm_response.data:
                # Check if message exists locally by supabase_id
                existing_dm = DirectMessage.query.filter_by(supabase_id=dm_data.get('id')).first()
                if not existing_dm:
                    # Check if message exists locally by local_id
                    local_id = dm_data.get('local_id')
                    if local_id:
                        existing_dm = DirectMessage.query.filter_by(id=local_id).first()
                    
                    if not existing_dm:
                        # Create message locally
                        try:
                            timestamp = datetime.fromisoformat(dm_data.get('timestamp'))
                        except:
                            timestamp = datetime.utcnow()
                            
                        direct_message = DirectMessage(
                            content=dm_data.get('content'),
                            raw_content=dm_data.get('raw_content'),
                            sender_id=dm_data.get('sender_id'),
                            recipient_id=dm_data.get('recipient_id'),
                            timestamp=timestamp,
                            is_read=dm_data.get('is_read', False),
                            supabase_id=dm_data.get('id')
                        )
                        db.session.add(direct_message)
                    else:
                        # Update existing message with Supabase ID
                        existing_dm.supabase_id = dm_data.get('id')
        
        db.session.commit()
        print("Supabase data synchronization completed successfully")
    except Exception as e:
        print(f"Error synchronizing data from Supabase: {e}")
        db.session.rollback()

# Call sync on app startup
with app.app_context():
    sync_from_supabase()

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
        
        # If Supabase is configured, also create user there
        if supabase:
            try:
                # Store user in Supabase for cloud sync
                supabase.table('users').insert({
                    'id': user.id,
                    'username': user.username,
                    'display_name': user.display_name,
                    'created_at': user.created_at.isoformat()
                }).execute()
            except Exception as e:
                print(f"Error saving user to Supabase: {e}")
    
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

def upload_file_to_supabase(file):
    """Upload a file to Supabase Storage"""
    if not supabase:
        return None
    
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)
        
        # Verify the bucket exists, create if not
        bucket_name = 'profile_pictures'
        try:
            # Check if bucket exists by attempting to get its details
            supabase.storage.get_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' exists")
        except Exception as e:
            if "Not found" in str(e):
                # Create the bucket if it doesn't exist
                try:
                    supabase.storage.create_bucket(bucket_name, {'public': True})
                    print(f"Created bucket '{bucket_name}'")
                except Exception as create_error:
                    print(f"Error creating bucket: {create_error}")
                    return None
            else:
                print(f"Error checking bucket: {e}")
                return None
        
        # Upload to Supabase storage
        with open(file_path, 'rb') as f:
            response = supabase.storage.from_(bucket_name).upload(
                filename,
                f.read(),
                {'content-type': file.content_type}
            )
        
        # Get the public URL
        file_url = supabase.storage.from_(bucket_name).get_public_url(filename)
        return file_url
    except Exception as e:
        print(f"Error uploading file to Supabase: {e}")
        return None

def save_direct_message(sender_id, recipient_id, content):
    """Save a direct message to the database and Supabase"""
    processed_content = process_message_content(content)
    
    # Create the direct message in the local database
    direct_message = DirectMessage(
        content=processed_content,
        raw_content=content,
        sender_id=sender_id,
        recipient_id=recipient_id
    )
    db.session.add(direct_message)
    db.session.commit()
    
    # If Supabase is configured, also save message there
    if supabase:
        try:
            result = supabase.table('direct_messages').insert({
                'local_id': direct_message.id,
                'content': processed_content,
                'raw_content': content,
                'sender_id': sender_id,
                'recipient_id': recipient_id,
                'timestamp': direct_message.timestamp.isoformat(),
                'is_read': False
            }).execute()
            
            # Get the Supabase ID and update the local record
            if result.data and len(result.data) > 0:
                supabase_id = result.data[0]['id']
                direct_message.supabase_id = supabase_id
                db.session.commit()
        except Exception as e:
            print(f"Error saving direct message to Supabase: {e}")
    
    return direct_message

def get_direct_messages(user_id, other_user_id):
    """Get all direct messages between two users"""
    # Get messages where user is sender and other is recipient
    sent_messages = DirectMessage.query.filter_by(
        sender_id=user_id, 
        recipient_id=other_id,
        is_deleted=False
    ).all()
    
    # Get messages where user is recipient and other is sender
    received_messages = DirectMessage.query.filter_by(
        sender_id=other_id, 
        recipient_id=user_id,
        is_deleted=False
    ).all()
    
    # Combine and sort by timestamp
    all_messages = sent_messages + received_messages
    all_messages.sort(key=lambda msg: msg.timestamp)
    
    return all_messages

def format_direct_message_for_client(message):
    """Format direct message object for sending to client"""
    return {
        "id": message.id,
        "content": message.content,
        "raw_content": message.raw_content,
        "sender_id": message.sender_id,
        "recipient_id": message.recipient_id,
        "sender_username": message.sender.username,
        "sender_display_name": message.sender.display_name or message.sender.username,
        "sender_profile_picture": message.sender.profile_picture,
        "timestamp": message.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "edited_at": message.edited_at.strftime("%Y-%m-%d %H:%M:%S") if message.edited_at else None,
        "is_deleted": message.is_deleted,
        "is_read": message.is_read
    }

def save_message_to_supabase(message):
    """Save a message to Supabase for cloud sync"""
    if not supabase or not message:
        return
    
    try:
        result = supabase.table('messages').insert({
            'local_id': message.id,
            'content': message.content,
            'raw_content': message.raw_content,
            'sender': message.sender,
            'user_id': message.user_id,
            'timestamp': message.timestamp.isoformat(),
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'is_deleted': message.is_deleted,
            'room_id': message.room_id,
            'read_by': message.read_by
        }).execute()
        
        # Get the Supabase ID and update the local record
        if result.data and len(result.data) > 0:
            supabase_id = result.data[0]['id']
            message.supabase_id = supabase_id
            db.session.commit()
            return supabase_id
    except Exception as e:
        print(f"Error saving message to Supabase: {e}")
    
    return None

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
    
    # Sync to Supabase if configured
    if supabase and message.supabase_id:
        try:
            supabase.table('messages').update({
                'content': message.content,
                'raw_content': message.raw_content,
                'edited_at': message.edited_at.isoformat()
            }).eq('id', message.supabase_id).execute()
        except Exception as e:
            print(f"Error updating message in Supabase: {e}")
    # If message doesn't have supabase_id yet, save it
    elif supabase:
        save_message_to_supabase(message)
    
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
    
    # Sync to Supabase if configured
    if supabase and message.supabase_id:
        try:
            supabase.table('messages').update({
                'is_deleted': True,
                'content': message.content
            }).eq('id', message.supabase_id).execute()
        except Exception as e:
            print(f"Error updating message deletion in Supabase: {e}")
    # If message doesn't have supabase_id yet, save it
    elif supabase:
        save_message_to_supabase(message)
    
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
    
    # Save to Supabase for cloud sync
    if supabase:
        save_message_to_supabase(new_message)
    
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
    user_id = session.get("user_id")
    
    # If user is authenticated, join their personal room for direct messages
    if user_id:
        personal_room = f"user_{user_id}"
        join_room(personal_room)
        print(f"User {name} joined personal room {personal_room}")
    
    # If in a chat room, join that room
    if room and name:
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

# Direct Message Routes
@app.route("/messages")
def messages_dashboard():
    if "name" not in session or "user_id" not in session:
        return redirect(url_for("home"))
    
    user_id = session["user_id"]
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for("home"))
    
    # Get all users for the contact list
    all_users = User.query.filter(User.id != user_id).all()
    
    # Get conversations (users with whom the current user has exchanged messages)
    sent_msgs = db.session.query(DirectMessage.recipient_id).filter_by(sender_id=user_id).distinct().all()
    received_msgs = db.session.query(DirectMessage.sender_id).filter_by(recipient_id=user_id).distinct().all()
    
    conversation_user_ids = set([r[0] for r in sent_msgs] + [r[0] for r in received_msgs])
    conversations = User.query.filter(User.id.in_(conversation_user_ids)).all() if conversation_user_ids else []
    
    # Get unread message counts for each conversation
    unread_counts = {}
    for conv_user in conversations:
        count = DirectMessage.query.filter_by(
            sender_id=conv_user.id,
            recipient_id=user_id,
            is_read=False
        ).count()
        unread_counts[conv_user.id] = count
    
    return render_template(
        "messages.html",
        user=user,
        conversations=conversations,
        all_users=all_users,
        unread_counts=unread_counts
    )

@app.route("/messages/<int:user_id>")
def direct_messages(user_id):
    if "name" not in session or "user_id" not in session:
        return redirect(url_for("home"))
    
    current_user_id = session["user_id"]
    current_user = User.query.get(current_user_id)
    other_user = User.query.get(user_id)
    
    if not current_user or not other_user:
        return redirect(url_for("messages_dashboard"))
    
    # Get all messages between the two users
    messages = get_direct_messages(current_user_id, user_id)
    formatted_messages = [format_direct_message_for_client(msg) for msg in messages]
    
    # Mark messages as read
    unread_messages = DirectMessage.query.filter_by(
        sender_id=user_id,
        recipient_id=current_user_id,
        is_read=False
    ).all()
    
    for msg in unread_messages:
        msg.is_read = True
        # Update in Supabase if configured
        if supabase and msg.supabase_id:
            try:
                supabase.table('direct_messages').update({
                    'is_read': True
                }).eq('id', msg.supabase_id).execute()
            except Exception as e:
                print(f"Error updating message read status in Supabase: {e}")
    
    db.session.commit()
    
    # Get all users for the sidebar
    all_users = User.query.filter(User.id != current_user_id).all()
    
    # Get conversations 
    sent_msgs = db.session.query(DirectMessage.recipient_id).filter_by(sender_id=current_user_id).distinct().all()
    received_msgs = db.session.query(DirectMessage.sender_id).filter_by(recipient_id=current_user_id).distinct().all()
    
    conversation_user_ids = set([r[0] for r in sent_msgs] + [r[0] for r in received_msgs])
    conversations = User.query.filter(User.id.in_(conversation_user_ids)).all() if conversation_user_ids else []
    
    # Get unread message counts for each conversation
    unread_counts = {}
    for conv_user in conversations:
        count = DirectMessage.query.filter_by(
            sender_id=conv_user.id,
            recipient_id=current_user_id,
            is_read=False
        ).count()
        unread_counts[conv_user.id] = count
    
    return render_template(
        "direct_messages.html",
        current_user=current_user,
        other_user=other_user,
        messages=formatted_messages,
        conversations=conversations,
        all_users=all_users,
        unread_counts=unread_counts
    )

@app.route("/api/messages/<int:recipient_id>", methods=["POST"])
def send_direct_message(recipient_id):
    if "name" not in session or "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    sender_id = session["user_id"]
    recipient = User.query.get(recipient_id)
    
    if not recipient:
        return jsonify({"error": "Recipient not found"}), 404
    
    data = request.json
    content = data.get("content")
    
    if not content or not content.strip():
        return jsonify({"error": "Message content required"}), 400
    
    # Save the message
    direct_message = save_direct_message(sender_id, recipient_id, content)
    
    # Format the message for response
    formatted_message = format_direct_message_for_client(direct_message)
    
    # Emit the message via Socket.IO to the recipient if they're online
    socketio.emit(
        "direct_message", 
        formatted_message,
        to=f"user_{recipient_id}"
    )
    
    return jsonify({"success": True, "message": formatted_message})

@app.route("/api/messages/<int:message_id>/read", methods=["POST"])
def mark_direct_message_read(message_id):
    if "name" not in session or "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_id = session["user_id"]
    message = DirectMessage.query.get(message_id)
    
    if not message:
        return jsonify({"error": "Message not found"}), 404
    
    # Only the recipient can mark as read
    if message.recipient_id != user_id:
        return jsonify({"error": "Not authorized"}), 403
    
    message.is_read = True
    db.session.commit()
    
    # Update in Supabase if configured
    if supabase and message.supabase_id:
        try:
            supabase.table('direct_messages').update({
                'is_read': True
            }).eq('id', message.supabase_id).execute()
        except Exception as e:
            print(f"Error updating message read status in Supabase: {e}")
    
    # Emit read receipt via Socket.IO
    socketio.emit(
        "direct_message_read", 
        {
            "message_id": message.id,
            "reader_id": user_id
        },
        to=f"user_{message.sender_id}"
    )
    
    return jsonify({"success": True})

@socketio.on("direct_message_send")
def handle_direct_message(data):
    if "user_id" not in session:
        return
    
    sender_id = session["user_id"]
    recipient_id = data.get("recipient_id")
    content = data.get("content")
    
    if not recipient_id or not content:
        return
    
    # Save the message
    direct_message = save_direct_message(sender_id, recipient_id, content)
    
    # Format the message for sending
    formatted_message = format_direct_message_for_client(direct_message)
    
    # Emit to sender and recipient
    socketio.emit(
        "direct_message", 
        formatted_message,
        to=f"user_{sender_id}"
    )
    
    socketio.emit(
        "direct_message", 
        formatted_message,
        to=f"user_{recipient_id}"
    )

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
else:
    # This branch will be used by Gunicorn when deployed on Render
    pass
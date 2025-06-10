# Enhanced Chat Application

A real-time chat application with enhanced features like message reactions, markdown support, and user profiles.

## Features

- **Real-time messaging** with Socket.IO
- **Message reactions** (emojis)
- **Message editing and deletion**
- **Markdown formatting** for messages
- **Read receipts** to see when messages are read
- **User profiles** with customizable display names and profile pictures
- **Theme switching** (light/dark mode)
- **User settings** that persist across sessions
- **Public and private rooms**

## Setup and Installation

1. Clone the repository
2. Install required dependencies:
   ```
   pip install flask flask-socketio flask-sqlalchemy bleach markdown
   ```
   Alternatively, you can use the provided requirements.txt:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python main.py
   ```
4. Open your browser and navigate to `http://localhost:5001`

## Usage

### Creating a Room
1. Enter your username
2. Click on "Create Room"
3. Choose whether to make the room public or private
4. Share the room code with others to join

### Joining a Room
1. Enter your username
2. Enter the room code
3. Click "Join Room"

### Using Markdown in Messages
You can format your messages using Markdown:
- **Bold**: `**text**`
- *Italic*: `*text*`
- ~~Strikethrough~~: `~~text~~`
- `Code`: `` `code` ``
- Code blocks: ` ```code blocks``` `
- And more!

### Message Reactions
1. Hover over a message
2. Click the emoji button
3. Select an emoji from the picker

### Editing Messages
1. Hover over your message
2. Click the edit button (pencil icon)
3. Make your changes
4. Click "Save Changes"

### Deleting Messages
1. Hover over your message
2. Click the delete button (trash icon)
3. Confirm deletion

## Deployment

To deploy this application to Render:

1. Create a Render account
2. Set up a Web Service pointing to your repository
3. Configure environment variables:
   - `SECRET_KEY`: A secure random string for session encryption
4. Create a PostgreSQL database in Render (or use the one in the render.yaml)
5. Deploy!

## Technologies Used

- **Backend**: Flask, Flask-SocketIO, SQLAlchemy
- **Frontend**: HTML, CSS, JavaScript
- **Database**: SQLite (development), PostgreSQL (production)

## License

This project is licensed under the MIT License.

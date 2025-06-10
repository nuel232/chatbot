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
- **Cloud synchronization** with Supabase

## Setup and Installation

1. Clone the repository
2. Install required dependencies:
   ```
   pip install flask flask-socketio flask-sqlalchemy bleach markdown supabase
   ```
   Alternatively, you can use the provided requirements.txt:
   ```
   pip install -r requirements.txt
   ```
3. Configure Supabase (optional but recommended):
   - Create a Supabase account at https://supabase.io
   - Create a new project
   - Get your project URL and anon key from the API settings
   - Set the environment variables:
     ```
     export SUPABASE_URL=your-project-url
     export SUPABASE_KEY=your-anon-key
     ```
   - Create the following tables in Supabase:
     - `users`: For user data
     - `rooms`: For room data
     - `messages`: For room messages
     - `direct_messages`: For private messages
   - Create a storage bucket named `profile_pictures` for user profile images
   
4. Run the application:
   ```
   python main.py
   ```
5. Open your browser and navigate to `http://localhost:5001`

## Supabase Configuration

The application can run with or without Supabase integration. When Supabase is configured:

1. **User data** is synchronized between local database and Supabase
2. **Messages** are stored both locally and in Supabase for backup and cross-device sync
3. **Profile pictures** are stored in Supabase Storage
4. **Direct messages** are synchronized for access across devices

To deploy on Vercel with Supabase, add the following environment variables in your Vercel project:
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase anon key

### Required Supabase Tables Schema

1. **users**:
   - id: int
   - username: string
   - display_name: string
   - created_at: timestamptz

2. **rooms**:
   - id: string
   - creator: string
   - is_public: boolean
   - created_at: timestamptz

3. **messages**:
   - id: uuid (auto-generated)
   - local_id: int
   - content: string
   - raw_content: string
   - sender: string
   - user_id: int
   - timestamp: timestamptz
   - edited_at: timestamptz
   - is_deleted: boolean
   - room_id: string
   - read_by: json

4. **direct_messages**:
   - id: uuid (auto-generated)
   - local_id: int
   - content: string
   - raw_content: string
   - sender_id: int
   - recipient_id: int
   - timestamp: timestamptz
   - is_read: boolean

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

## Technologies Used

- **Backend**: Flask, Flask-SocketIO, SQLAlchemy
- **Frontend**: HTML, CSS, JavaScript
- **Database**: SQLite (default), can be configured for other databases

## License

This project is licensed under the MIT License. # chatbot
# chatbot

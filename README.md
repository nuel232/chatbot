# Simple Chat Application

A lightweight real-time chat application with browser caching.

## Features

- **Real-time messaging** with Socket.IO
- **Message editing and deletion**
- **Markdown formatting** for messages
- **Public and private rooms**
- **No user authentication required**
- **Browser-based message storage**

## Setup and Installation

1. Clone the repository
2. Install required dependencies:
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
1. Enter your name
2. Click on "Create Room"
3. Choose whether to make the room public or private
4. Share the room code with others to join

### Joining a Room
1. Enter your name
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
4. Deploy!

### Deployment Troubleshooting

If you encounter issues with the Render deployment:

1. Check that your `render.yaml` is correctly configured with `startCommand: gunicorn main:app`
2. Ensure you have both `app.py` and `wsgi.py` in your repository as alternative entry points
3. Make sure your Procfile has the correct command: `web: gunicorn -k eventlet -w 1 main:app`
4. If you see a "No module named 'app'" error, try uncommenting the alternative start command in `render.yaml`
5. For Socket.IO applications, ensure you're using the eventlet worker: `-k eventlet -w 1`

## Technologies Used

- **Backend**: Flask, Flask-SocketIO
- **Frontend**: HTML, CSS, JavaScript

## License

This project is licensed under the MIT License.

from flask import request, current_app
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from app import socketio, db
from app.models import Message, Chat, User, Notification
import json
from datetime import datetime
import os
import uuid
from app.utils import secure_filename

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        # Join a personal room for private notifications
        join_room(f'user_{current_user.id}')
        print(f'User {current_user.username} connected')

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        print(f'User {current_user.username} disconnected')

@socketio.on('join_chat')
def handle_join_chat(data):
    chat_id = data.get('chat_id')
    
    if not current_user.is_authenticated or not chat_id:
        return
    
    chat = Chat.query.get(chat_id)
    
    if not chat or current_user not in chat.members:
        emit('error', {'message': 'Not authorized to join this chat'})
        return
    
    join_room(f'chat_{chat_id}')
    print(f'User {current_user.username} joined chat {chat_id}')

@socketio.on('leave_chat')
def handle_leave_chat(data):
    chat_id = data.get('chat_id')
    
    if not current_user.is_authenticated or not chat_id:
        return
    
    leave_room(f'chat_{chat_id}')
    print(f'User {current_user.username} left chat {chat_id}')

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

    chat_id = data.get('chat_id')
    text = data.get('text', '').strip()
    file_data = data.get('file_data') # Expecting { 'name': 'filename.ext', 'content': ArrayBuffer/Blob }
    file_name = data.get('file_name')

    if not chat_id:
        current_app.logger.warning(f"send_message: Chat ID missing. User: {current_user.id}")
        emit('error', {'message': 'Chat ID missing'})
        return

    if not text and not file_data:
        current_app.logger.warning(f"send_message: Empty message (no text/file). User: {current_user.id}, Chat: {chat_id}")
        emit('error', {'message': 'Message text or file is required'})
        return

    chat = Chat.query.get(chat_id)
    if not chat or current_user not in chat.members:
        current_app.logger.warning(f"send_message: Auth error or chat not found. User: {current_user.id}, Chat: {chat_id}")
        emit('error', {'message': 'Not authorized to send messages to this chat'})
        return

    saved_file_path = None
    if file_data and file_name:
        try:
            filename = secure_filename(f"{uuid.uuid4()}_{file_name}")
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            
            # file_data is expected to be bytes (e.g., from ArrayBuffer on client)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            saved_file_path = filename
        except Exception as e:
            current_app.logger.warning(f"IMPORTANT! File upload failed for user {current_user.username} in chat {chat_id}")
            emit('error', {'message': 'File upload failed'})
            # Optionally, do not proceed with message saving if file upload is critical and failed
            # return 
    
    message = Message(
        text=text if text else None, # Store None if text is empty
        user_id=current_user.id,
        chat_id=chat.id,
        file=saved_file_path,
        timestamp=datetime.now()
    )
    db.session.add(message)
    db.session.commit()

    emit('new_message', {
        'id': message.id,
        'text': message.text,
        'timestamp': message.timestamp.isoformat(),
        'user_id': message.user_id,
        'username': message.author.username, # Use message.author for consistency
        'user_avatar': message.author.avatar,
        'file': message.file, # This will be the server path
        'chat_id': chat.id
    }, room=f'chat_{chat_id}')
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

@socketio.on('notification')
def handle_notification(data):
    user_id = data.get('user_id')
    
    if not user_id:
        return
    
    # Broadcast notification to the specific user
    emit('new_notification', {
        'count': Notification.query.filter_by(user_id=user_id, dismissed=False).count()
    }, room=f'user_{user_id}')

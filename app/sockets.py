from flask import request, current_app
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from app import socketio, db
from app.models import Message, Chat, User, Notification
import json
from datetime import datetime

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
        return
    
    chat_id = data.get('chat_id')
    text = data.get('text')
    file_path = data.get('file_path', None)
    
    if not chat_id or not text:
        emit('error', {'message': 'Missing required fields'})
        return
    
    chat = Chat.query.get(chat_id)
    
    if not chat or current_user not in chat.members:
        emit('error', {'message': 'Not authorized to send messages to this chat'})
        return
    
    # Create and save message
    message = Message(
        text=text,
        user_id=current_user.id,
        chat_id=chat_id,
        file=file_path,
        timestamp=datetime.utcnow()
    )
    db.session.add(message)
    db.session.commit()
    
    # Broadcast to all members in the chat room
    emit('new_message', {
        'id': message.id,
        'text': message.text,
        'timestamp': message.timestamp.isoformat(),
        'user_id': message.user_id,
        'username': current_user.username,
        'file': message.file,
        'avatar': current_user.avatar
    }, room=f'chat_{chat_id}')

@socketio.on('notification')
def handle_notification(data):
    user_id = data.get('user_id')
    
    if not user_id:
        return
    
    # Broadcast notification to the specific user
    emit('new_notification', {
        'count': Notification.query.filter_by(user_id=user_id, dismissed=False).count()
    }, room=f'user_{user_id}')

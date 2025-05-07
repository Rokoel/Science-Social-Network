from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import current_user, login_required
from app import db, limiter
from app.models import Chat, Message, Project, User, Notification
from app.forms import MessageForm, ChatForm
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime

chats_bp = Blueprint('chats', __name__, url_prefix='/chats')

@chats_bp.route('/<int:id>', methods=['GET', 'POST'])
@login_required
def view(id):
    chat = Chat.query.get_or_404(id)
    project = chat.project
    
    # Ensure user is a member of the chat
    if current_user not in chat.members:
        flash('You are not a member of this chat.')
        return redirect(url_for('projects.view', id=project.id))
    
    form = MessageForm()
    
    if form.validate_on_submit():
        # Handle file upload
        file_path = None
        if form.file.data:
            filename = secure_filename(f"{uuid.uuid4()}_{form.file.data.filename}")
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            form.file.data.save(filepath)
            file_path = filename
        
        message = Message(
            text=form.text.data,
            user_id=current_user.id,
            chat_id=chat.id,
            file=file_path,
            timestamp=datetime.utcnow()
        )
        db.session.add(message)
        db.session.commit()
        
        # Clear form
        form.text.data = ''
        form.file.data = None
    
    # Get messages with pagination
    page = request.args.get('page', 1, type=int)
    messages = Message.query.filter_by(chat_id=chat.id).order_by(
        Message.timestamp.desc()
    ).paginate(page=page, per_page=50)
    
    return render_template('chats/chat.html',
                          title=chat.name,
                          chat=chat,
                          project=project,
                          messages=messages,
                          form=form)

@chats_bp.route('/create/<int:project_id>', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour")
def create(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check if user is an admin
    if current_user not in project.admins:
        flash('Only project admins can create new chats.')
        return redirect(url_for('projects.view', id=project.id))
    
    form = ChatForm()
    
    if form.validate_on_submit():
        chat = Chat(
            name=form.name.data,
            creator_id=current_user.id,
            project_id=project.id
        )
        
        # Add all project members to the chat by default
        chat.members = project.members.copy()
        
        db.session.add(chat)
        db.session.commit()
        
        # Notify all project members about the new chat
        for member in project.members:
            if member.id != current_user.id:
                notification = Notification(
                    user_id=member.id,
                    sender_id=current_user.id,
                    notification_type='info',
                    info_type='new_chat',
                    text=f"New chat '{chat.name}' created in project '{project.title}'",
                    chat_id=chat.id
                )
                db.session.add(notification)
        
        db.session.commit()
        flash(f"Chat '{chat.name}' has been created!")
        return redirect(url_for('chats.view', id=chat.id))
    
    return render_template('chats/create_chat.html',
                          title='Create Chat',
                          form=form,
                          project=project)

@chats_bp.route('/<int:id>/invite/<int:user_id>')
@login_required
def invite_user(id, user_id):
    chat = Chat.query.get_or_404(id)
    project = chat.project
    user = User.query.get_or_404(user_id)
    
    # Ensure current user is an admin of the project
    if current_user not in project.admins:
        flash('Only project admins can invite users to chats.')
        return redirect(url_for('chats.view', id=chat.id))
    
    # Ensure target user is a member of the project
    if user not in project.members:
        flash('User must be a project member to be invited to chat.')
        return redirect(url_for('chats.view', id=chat.id))
    
    # Check if user is already in the chat
    if user in chat.members:
        flash('User is already a member of this chat.')
        return redirect(url_for('chats.view', id=chat.id))
    
    # Create an invitation notification
    notification = Notification(
        user_id=user.id,
        sender_id=current_user.id,
        notification_type='invite',
        invite_type='chat',
        text=f"You've been invited to join the chat '{chat.name}' in project '{project.title}'",
        chat_id=chat.id
    )
    db.session.add(notification)
    db.session.commit()
    
    flash(f"Invitation sent to {user.username}.")
    return redirect(url_for('chats.view', id=chat.id))

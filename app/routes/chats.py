from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import current_user, login_required
from app import db, limiter, socketio
from app.models import Chat, Message, Project, User, Notification
from app.forms import MessageForm, ChatForm
from app.utils import secure_filename
import os
import uuid
from datetime import datetime

chats_bp = Blueprint('chats', __name__, url_prefix='/chats')

@chats_bp.route('/<int:id>', methods=['GET', 'POST'])
@login_required
def view(id):
    chat = Chat.query.get_or_404(id)
    project = chat.project # Assuming chat always has a project

    if current_user not in chat.members:
        flash("You are not a member of this chat.")
        return redirect(url_for("projects.view", id=project.id))

    form = MessageForm() # Form is still passed to the template

    page = request.args.get("page", 1, type=int)
    messages = (
        Message.query.filter_by(chat_id=chat.id)
        .order_by(Message.timestamp.desc())
        .paginate(page=page, per_page=50)
    )

    return render_template(
        "chats/chat.html",
        title=chat.name,
        chat=chat,
        project=project,
        messages=messages,
        form=form,
    )

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

@chats_bp.route('/<int:chat_id>/leave')
@login_required
def leave_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    project = Project.query.get_or_404(chat.project_id) # Get project for context

    if current_user not in chat.members:
        flash("You are not a member of this chat.")
        return redirect(url_for('projects.view', id=project.id)) # Redirect to project

    # Chat creator cannot leave if they are the only admin of the chat (if chats had admins)
    # For now, let's assume project admins manage chats.
    # If chat creator is the only member, perhaps the chat should be deleted or archived (future feature).
    # For now, allow leaving.

    if current_user == chat.creator and len(chat.members) == 1:
        # Allow leaving, flash a warning and delete the chat
        flash("You are the only member of this chat. The chat will be deleted.")
        db.session.delete(chat)
        db.session.commit()
        pass

    chat.members.remove(current_user)
    db.session.commit()
    flash(f"You have left the chat '{chat.name}'.")


    return redirect(url_for('projects.view', id=project.id))


@chats_bp.route('/<int:chat_id>/kick/<int:user_id>')
@login_required
def kick_user_from_chat(chat_id, user_id):
    chat = Chat.query.get_or_404(chat_id)
    user_to_kick = User.query.get_or_404(user_id)
    project = Project.query.get_or_404(chat.project_id)

    # Authorization: Only project admins can kick from project chats
    # Or, if chats had their own admins: if current_user is a chat admin
    if current_user not in project.admins:
        flash("You are not authorized to kick members from this chat.")
        return redirect(url_for('chats.view', id=chat.id))

    if user_to_kick not in chat.members:
        flash(f"{user_to_kick.username} is not a member of this chat.")
        return redirect(url_for('chats.view', id=chat.id))

    if user_to_kick == current_user:
        flash("You cannot kick yourself. Use the 'Leave Chat' option.")
        return redirect(url_for('chats.view', id=chat.id))
    
    # Prevent kicking the chat creator by other project admins
    if user_to_kick == chat.creator and current_user != chat.creator:
         flash(f"The chat creator ({user_to_kick.username}) cannot be kicked by other admins.")
         return redirect(url_for('chats.view', id=chat.id))


    chat.members.remove(user_to_kick)
    db.session.commit()
    flash(f"{user_to_kick.username} has been kicked from the chat '{chat.name}'.")

    # Notify the kicked user
    kicked_user_notification = Notification(
        user_id=user_to_kick.id,
        sender_id=current_user.id,
        notification_type='info',
        info_type='kicked_from_chat',
        text=f"You have been removed from the chat '{chat.name}' by {current_user.username}.",
        chat_id=chat.id,
        project_id=project.id
    )
    db.session.add(kicked_user_notification)
    db.session.commit()
    socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=user_to_kick.id, dismissed=False).count()}, room=f'user_{user_to_kick.id}')

    return redirect(url_for('chats.view', id=chat.id))

@chats_bp.route('/<int:chat_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    project = Project.query.get_or_404(chat.project_id) # For redirect and auth context

    # Authorization: Only chat creator OR a project admin can delete the chat
    if not (current_user.id == chat.creator_id or current_user in project.admins):
        flash('You are not authorized to delete this chat.')
        return redirect(url_for('chats.view', id=chat.id))
    
    # Prevent deleting the last default chat of a project (optional rule)
    # Example: if chat.name == f"{project.title} Chat (General)" and project.chats.count() == 1:
    #     flash("Cannot delete the last default chat of the project.")
    #     return redirect(url_for('projects.view', id=project.id))

    try:
        # Delete associated notifications for this chat (optional)
        Notification.query.filter_by(chat_id=chat.id).delete()
        # Messages are set to cascade delete via SQLAlchemy relationship with Chat.

        db.session.delete(chat)
        db.session.commit()
        flash(f"Chat '{chat.name}' has been deleted.")
        return redirect(url_for('projects.view', id=project.id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting chat {chat_id}: {str(e)}", exc_info=True)
        flash("An error occurred while trying to delete the chat. Please try again.")
        return redirect(url_for('chats.view', id=chat.id))
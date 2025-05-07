from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request
from flask_login import current_user, login_required
from app import db, limiter
from app.models import Notification, Chat, Project
from datetime import datetime

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('/feed')
@login_required
def feed():
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        dismissed=False
    ).order_by(Notification.timestamp.desc()).all()
    
    return jsonify([{
        'id': n.id,
        'text': n.text,
        'timestamp': n.timestamp.isoformat(),
        'type': n.notification_type,
        'status': n.status,
        'sender': {
            'id': n.sender.id,
            'username': n.sender.username
        } if n.sender else None,
        'chat_id': n.chat_id
    } for n in notifications])

@notifications_bp.route('/<int:id>/dismiss')
@login_required
def dismiss(id):
    notification = Notification.query.get_or_404(id)
    
    # Ensure notification belongs to current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    
    notification.dismissed = True
    db.session.commit()
    
    return jsonify({'success': True})

@notifications_bp.route('/<int:id>/accept')
@login_required
def accept(id):
    notification = Notification.query.get_or_404(id)
    
    # Ensure notification belongs to current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    
    # Only invitations can be accepted
    if notification.notification_type != 'invite':
        return jsonify({'success': False, 'message': 'Only invitations can be accepted'}), 400
    
    # Handle different invitation types
    if notification.invite_type == 'chat':
        chat = Chat.query.get(notification.chat_id)
        if chat:
            chat.members.append(current_user)
            notification.status = 'accepted'
            db.session.commit()
            return jsonify({'success': True, 'redirect': url_for('chats.view', id=chat.id)})
    
    return jsonify({'success': False, 'message': 'Invalid invitation type'})

@notifications_bp.route('/<int:id>/reject')
@login_required
def reject(id):
    notification = Notification.query.get_or_404(id)
    
    # Ensure notification belongs to current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    
    # Only invitations can be rejected
    if notification.notification_type != 'invite':
        return jsonify({'success': False, 'message': 'Only invitations can be rejected'}), 400
    
    notification.status = 'rejected'
    db.session.commit()
    
    return jsonify({'success': True})

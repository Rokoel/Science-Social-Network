from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request, current_app
from flask_login import current_user, login_required
from app import db, limiter, socketio
from app.models import Notification, Chat, Project, User
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

@notifications_bp.route('/<int:id>/dismiss', methods=['POST'])
@login_required
def dismiss(id):
    notification = Notification.query.get_or_404(id)
    
    # Ensure notification belongs to current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    
    notification.dismissed = True
    db.session.commit()
    
    return jsonify({'success': True})

@notifications_bp.route('/<int:id>/accept', methods=['POST'])
@login_required
def accept(id):
    notification = Notification.query.get_or_404(id)
    
    if notification.user_id != current_user.id: # Current user must be the recipient of notification
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
    
    if notification.notification_type != 'invite':
        return jsonify({'success': False, 'message': 'Only invitations can be accepted'}), 400
    
    if notification.status != 'not_answered':
        return jsonify({'success': False, 'message': 'This invitation has already been responded to.'}), 400

    success = False
    redirect_url = None
    applicant = None # For project applications

    redirect_url = None
    response_data = {'success': False, 'message': 'Processing failed.'} # Default error response

    if notification.invite_type == 'chat':
        chat = Chat.query.get(notification.chat_id)
        if not chat:
            response_data['message'] = 'Associated chat not found.'
            return jsonify(response_data), 404

        try:
            if current_user not in chat.members:
                chat.members.append(current_user)
            
            notification.status = 'accepted'
            notification.dismissed = True
            # db.session.commit() # Commit will happen after inviter notification

            redirect_url = url_for('chats.view', id=chat.id)
            
            if notification.sender_id and notification.sender_id != current_user.id:
                original_inviter = User.query.get(notification.sender_id)
                if original_inviter:
                    accepted_noti_to_inviter = Notification(
                        user_id=original_inviter.id, sender_id=current_user.id,
                        notification_type='info', info_type='chat_invite_accepted_by_user',
                        text=f"{current_user.username} accepted your invitation to join the chat '{chat.name}'.",
                        chat_id=chat.id, project_id=chat.project_id
                    )
                    db.session.add(accepted_noti_to_inviter)
                else:
                    current_app.logger.warning(f"ACCEPT: Original inviter (ID: {notification.sender_id}) not found for chat invite acceptance.")
            
            db.session.commit() # Commit all changes for this block
            success = True
            response_data = {'success': True, 'redirect': redirect_url}

            # Emit socket event after successful commit and response prep
            if notification.sender_id and notification.sender_id != current_user.id and original_inviter:
                socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=original_inviter.id, dismissed=False).count()}, room=f'user_{original_inviter.id}')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"ACCEPT: Exception during 'chat' invite processing for notif ID {id}: {str(e)}", exc_info=True)
            response_data['message'] = f'An internal error occurred: {str(e)}'
            return jsonify(response_data), 500

    elif notification.invite_type == 'project_application':
        project = Project.query.get(notification.project_id)
        applicant = User.query.get(notification.sender_id) # User who applied

        if project and applicant and current_user == project.creator: # current_user is project creator
            if applicant not in project.members:
                project.members.append(applicant)
                # Add to default chat(s)
                default_chats = Chat.query.filter_by(project_id=project.id, name=f"{project.title} Chat").all()
                for default_chat in default_chats:
                    if applicant not in default_chat.members:
                        default_chat.members.append(applicant)
            
            notification.status = 'accepted'
            
            # Notify applicant
            applicant_notification = Notification(
                user_id=applicant.id,
                sender_id=current_user.id, # Project creator
                notification_type='info',
                info_type='project_application_accepted',
                text=f"Your application to project '{project.title}' has been accepted.",
                project_id=project.id
            )
            db.session.add(applicant_notification)
            notification.dismissed = True
            db.session.commit()
            success = True
            # No specific redirect for creator, but applicant gets notified
            socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=applicant.id, dismissed=False).count()}, room=f'user_{applicant.id}')
        else:
            return jsonify({'success': False, 'message': 'Invalid project application or not authorized.'}), 400
            
    if success:
        return jsonify({'success': True, 'redirect': redirect_url})
    else:
        return jsonify({'success': False, 'message': 'Could not process acceptance.'}), 500

@notifications_bp.route('/<int:id>/reject', methods=['POST'])
@login_required
def reject(id):
    notification = Notification.query.get_or_404(id)
    
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Not authorized'}), 403
        
    if notification.notification_type != 'invite':
        return jsonify({'success': False, 'message': 'Only invitations can be rejected'}), 400

    if notification.status != 'not_answered':
        return jsonify({'success': False, 'message': 'This invitation has already been responded to.'}), 400

    notification.status = 'rejected'
    success = False

    response_data = {'success': False, 'message': 'Processing failed.'}

    if notification.invite_type == 'chat':
        chat = Chat.query.get(notification.chat_id)
        try:
            notification.status = 'rejected' 
            notification.dismissed = True 

            if notification.sender_id and notification.sender_id != current_user.id:
                original_inviter = User.query.get(notification.sender_id)
                if original_inviter:
                    rejected_noti_to_inviter = Notification(
                        user_id=original_inviter.id, sender_id=current_user.id,
                        notification_type='info', info_type='chat_invite_rejected_by_user',
                        text=f"{current_user.username} rejected your invitation to join the chat '{chat.name if chat else 'an unknown chat'}'.",
                        chat_id=notification.chat_id, project_id=chat.project_id if chat else None
                    )
                    db.session.add(rejected_noti_to_inviter)
                else:
                    current_app.logger.warning(f"REJECT: Original inviter (ID: {notification.sender_id}) not found for chat invite rejection.")
            
            db.session.commit()
            response_data = {'success': True}
            success = True

            if notification.sender_id and notification.sender_id != current_user.id and original_inviter:
                socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=original_inviter.id, dismissed=False).count()}, room=f'user_{original_inviter.id}')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"REJECT: Exception during 'chat' invite processing for notif ID {id}: {str(e)}", exc_info=True)
            response_data['message'] = f'An internal error occurred: {str(e)}'
            return jsonify(response_data), 500

    elif notification.invite_type == 'project_application':
        project = Project.query.get(notification.project_id)
        applicant = User.query.get(notification.sender_id) # User who applied

        if project and applicant and current_user == project.creator:
            # Notify applicant
            applicant_notification = Notification(
                user_id=applicant.id,
                sender_id=current_user.id,
                notification_type='info',
                info_type='project_application_rejected',
                text=f"Your application to project '{project.title}' has been rejected.",
                project_id=project.id
            )
            db.session.add(applicant_notification)
            socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=applicant.id, dismissed=False).count()}, room=f'user_{applicant.id}')
            success = True
        else:
             return jsonify({'success': False, 'message': 'Invalid project application or not authorized.'}), 400

    if success:
        notification.dismissed = True
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Could not process rejection.'}), 500

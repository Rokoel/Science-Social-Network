from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import current_user, login_required
from app import db, limiter, socketio
from app.models import Project, User, Chat, Notification
from app.forms import ProjectForm, SearchForm, EditProjectForm
from datetime import datetime
from sqlalchemy import or_

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')

VALID_PROJECT_TYPES = ["Project", "Experiment", "Study", "Other"]

@projects_bp.route('/feed')
@login_required
def feed():
    page = request.args.get('page', 1, type=int)
    topic = request.args.get('topic')
    deadline = request.args.get('deadline')
    
    query = Project.query.filter(Project.is_public == True)
    
    if topic:
        query = query.filter(or_(
            Project.title.ilike(f'%{topic}%'),
            Project.description.ilike(f'%{topic}%'),
            Project.project_type.ilike(f'%{topic}%')
        ))
        
    if deadline:
        try:
            deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
            query = query.filter(Project.deadline >= deadline_date)
        except ValueError:
            pass
    
    projects = query.order_by(Project.created_at.desc()).paginate(page=page, per_page=10)
    
    search_form = SearchForm()
    
    return render_template('projects/feed.html', 
                          title='Project Feed', 
                          projects=projects,
                          search_form=search_form)

@projects_bp.route('/create', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour")
def create():
    form = ProjectForm()
    if form.validate_on_submit():
        project_type_data = form.project_type.data
        if project_type_data not in VALID_PROJECT_TYPES:
            project_type_data = "Other"
        
        project = Project(
            title=form.title.data,
            description=form.description.data,
            goals=form.goals.data,
            creator_id=current_user.id,
            deadline=form.deadline.data,
            project_type=project_type_data,
            is_public=form.is_public.data
        )
        
        # Add creator as admin and member
        project.admins.append(current_user)
        project.members.append(current_user)
        
        db.session.add(project)
        db.session.commit()
        
        # Create default chat
        chat = Chat(name=f"{project.title} Chat", creator_id=current_user.id, project_id=project.id)
        chat.members.append(current_user)
        db.session.add(chat)
        db.session.commit()
        
        flash('Your project has been created!')
        return redirect(url_for('projects.view', id=project.id))
    
    return render_template('projects/create.html', title='Create Project', form=form)

@projects_bp.route('/<int:id>')
@login_required
def view(id):
    project = Project.query.get_or_404(id)
    
    if not project.is_public and current_user not in project.members:
        flash('This project is private.')
        return redirect(url_for('projects.feed'))
    
    is_admin = current_user in project.admins
    is_member = current_user in project.members
    
    # Query and sort chats here
    # Ensure Chat model is imported at the top of this file
    sorted_chats = []
    if is_member: # Only load chats if the user is a member
        sorted_chats = project.chats.order_by(Chat.created_at.desc()).all()
    
    return render_template('projects/view.html', 
                          title=project.title,
                          project=project,
                          is_admin=is_admin,
                          is_member=is_member,
                          sorted_chats=sorted_chats)

@projects_bp.route('/<int:id>/apply')
@login_required
def apply(id):
    project = Project.query.get_or_404(id)

    if not project.is_public:
        flash("This project is private and does not accept applications directly.")
        return redirect(url_for('projects.view', id=project.id))

    if current_user in project.members:
        flash('You are already a member of this project.')
        return redirect(url_for('projects.view', id=project.id))

    # Check if an application already exists and is pending
    existing_application = Notification.query.filter_by(
        sender_id=current_user.id,
        project_id=project.id,
        notification_type='invite', # Using 'invite' as it needs action
        invite_type='project_application',
        status='not_answered'
    ).first()

    if existing_application:
        flash('You have already applied to this project. Please wait for the creator to respond.')
        return redirect(url_for('projects.view', id=project.id))

    # Create notification for project creator
    notification = Notification(
        user_id=project.creator_id, # Notify the project creator
        sender_id=current_user.id,
        notification_type='invite', # Requires action from creator
        invite_type='project_application',
        text=f"User <a href='{url_for('users.view_profile', user_id=current_user.id)}'>{current_user.username}</a> has applied to join your project: '{project.title}'.",
        project_id=project.id,
        status='not_answered' # For the creator's action
    )
    db.session.add(notification)
    db.session.commit()

    # Notify project creator via Socket.IO about new notification
    socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=project.creator_id, dismissed=False).count()}, room=f'user_{project.creator_id}')


    flash('Your application has been sent to the project creator.')
    return redirect(url_for('projects.view', id=project.id))

@projects_bp.route('/<int:id>/leave')
@login_required
def leave(id):
    project = Project.query.get_or_404(id)
    
    if current_user.id == project.creator_id and len(project.admins) == 1 : # If creator is the only admin
        flash('As the sole admin and creator, you cannot leave the project. Promote another admin first or delete the project.')
        return redirect(url_for('projects.view', id=project.id))
    
    if current_user not in project.members:
        flash('You are not a member of this project.')
        return redirect(url_for('projects.view', id=project.id))
    
    original_admins = list(project.admins) # Copy before modification

    project.members.remove(current_user)
    if current_user in project.admins:
        project.admins.remove(current_user)
    
    for chat in project.chats:
        if current_user in chat.members:
            chat.members.remove(current_user)
    
    # Create notification for remaining project admins
    for admin in original_admins:
        if admin.id != current_user.id and admin in project.admins: # Ensure admin is still an admin
            notification = Notification(
                user_id=admin.id,
                sender_id=current_user.id, # Or system
                notification_type='info',
                info_type='member_left_project',
                text=f"{current_user.username} has left your project: {project.title}",
                project_id=project.id
            )
            db.session.add(notification)
            socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=admin.id, dismissed=False).count()}, room=f'user_{admin.id}')

    db.session.commit()
    flash('You have left the project.')
    return redirect(url_for('projects.feed'))

@projects_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    project = Project.query.get_or_404(id)

    if current_user != project.creator and current_user not in project.admins:
        flash('You are not authorized to edit this project.')
        return redirect(url_for('projects.view', id=project.id))

    form = EditProjectForm(original_title=project.title)

    if form.validate_on_submit():
        project_type_data = form.project_type.data
        if project_type_data not in VALID_PROJECT_TYPES:
            project_type_data = "Other"
        
        project.title = form.title.data
        project.description = form.description.data
        project.goals = form.goals.data
        project.deadline = form.deadline.data
        project.project_type = form.project_type.data
        project.is_public = form.is_public.data
        db.session.commit()
        flash('Your project has been updated!')
        return redirect(url_for('projects.view', id=project.id))
    elif request.method == 'GET':
        form.title.data = project.title
        form.description.data = project.description
        form.goals.data = project.goals
        form.deadline.data = project.deadline
        form.project_type.data = project.project_type
        form.is_public.data = project.is_public

    return render_template('projects/edit_project.html', title='Edit Project',
                           form=form, project=project)

@projects_bp.route('/search')
@login_required
def search():
    query = request.args.get('query', '')
    search_type = request.args.get('search_type', 'projects')
    
    if not query:
        return jsonify([])
    
    if search_type == 'projects':
        results = Project.query.filter(
            or_(
                Project.title.ilike(f'%{query}%'),
                Project.description.ilike(f'%{query}%')
            ),
            Project.is_public == True
        ).limit(10).all()
        
        return jsonify([{
            'id': p.id,
            'title': p.title,
            'description': p.description,
            'type': 'project'
        } for p in results])
    
    elif search_type == 'chats':
        # Only search chats the user is a member of
        results = Chat.query.join(
            Chat.members
        ).filter(
            User.id == current_user.id,
            Chat.name.ilike(f'%{query}%')
        ).limit(10).all()
        
        return jsonify([{
            'id': c.id,
            'name': c.name,
            'project_id': c.project_id,
            'project_title': c.project.title,
            'type': 'chat'
        } for c in results])
    
    return jsonify([])

@projects_bp.route('/<int:project_id>/manage_member/<int:user_id>/<action>')
@login_required
def manage_member(project_id, user_id, action):
    project = Project.query.get_or_404(project_id)
    user_to_manage = User.query.get_or_404(user_id)

    if current_user not in project.admins:
        flash('Only project admins can manage members.')
        return redirect(url_for('projects.view', id=project.id))

    if user_to_manage == project.creator and action == "remove":
        flash("The project creator cannot be removed by other admins.")
        return redirect(url_for('projects.view', id=project.id))
    
    if user_to_manage == current_user and action == "remove" and len(project.admins) == 1:
        flash("You cannot remove yourself as the sole admin.")
        return redirect(url_for('projects.view', id=project.id))


    notification_text = ""
    info_type_for_user = ""

    if action == 'make_admin':
        if user_to_manage not in project.members:
            flash(f'{user_to_manage.username} is not a member of this project.')
        elif user_to_manage in project.admins:
            flash(f'{user_to_manage.username} is already an admin.')
        else:
            project.admins.append(user_to_manage)
            db.session.commit()
            flash(f'{user_to_manage.username} is now an admin.')
            notification_text = f"You have been made an admin in project '{project.title}'."
            info_type_for_user = "made_project_admin"
    elif action == 'remove_admin':
        if user_to_manage == project.creator:
            flash("The project creator cannot lose admin rights unless they transfer ownership (not implemented).")
        elif user_to_manage not in project.admins:
            flash(f'{user_to_manage.username} is not an admin.')
        elif len(project.admins) == 1:
            flash(f"Cannot remove the last admin. Promote another member to admin first.")
        else:
            project.admins.remove(user_to_manage)
            db.session.commit()
            flash(f'{user_to_manage.username} is no longer an admin.')
            notification_text = f"You are no longer an admin in project '{project.title}'."
            info_type_for_user = "removed_project_admin"
    elif action == 'remove_member':
        if user_to_manage not in project.members:
            flash(f'{user_to_manage.username} is not a member of this project.')
        else:
            project.members.remove(user_to_manage)
            if user_to_manage in project.admins:
                project.admins.remove(user_to_manage)
            
            # Remove from all project chats
            for chat in project.chats:
                if user_to_manage in chat.members:
                    chat.members.remove(user_to_manage)
            
            db.session.commit()
            flash(f'{user_to_manage.username} has been removed from the project.')
            notification_text = f"You have been removed from project '{project.title}'."
            info_type_for_user = "removed_from_project"
    else:
        flash('Invalid action.')
        return redirect(url_for('projects.view', id=project.id))

    if notification_text and info_type_for_user and user_to_manage != current_user:
        noti = Notification(
            user_id=user_to_manage.id,
            sender_id=current_user.id,
            notification_type='info',
            info_type=info_type_for_user,
            text=notification_text,
            project_id=project.id
        )
        db.session.add(noti)
        db.session.commit()
        socketio.emit('new_notification', {'count': Notification.query.filter_by(user_id=user_to_manage.id, dismissed=False).count()}, room=f'user_{user_to_manage.id}')

    return redirect(url_for('projects.view', id=project.id))
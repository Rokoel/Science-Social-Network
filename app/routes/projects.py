from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import current_user, login_required
from app import db, limiter
from app.models import Project, User, Chat, Notification
from app.forms import ProjectForm, SearchForm, EditProjectForm
from datetime import datetime
from sqlalchemy import or_

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')

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
        project = Project(
            title=form.title.data,
            description=form.description.data,
            goals=form.goals.data,
            creator_id=current_user.id,
            deadline=form.deadline.data,
            project_type=form.project_type.data,
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
    
    # If project is private, check if user is a member
    if not project.is_public and current_user not in project.members:
        flash('This project is private.')
        return redirect(url_for('projects.feed'))
    
    is_admin = current_user in project.admins
    is_member = current_user in project.members
    
    return render_template('projects/view.html', 
                          title=project.title,
                          project=project,
                          is_admin=is_admin,
                          is_member=is_member)

@projects_bp.route('/<int:id>/join')
@login_required
def join(id):
    project = Project.query.get_or_404(id)
    
    if current_user in project.members:
        flash('You are already a member of this project.')
        return redirect(url_for('projects.view', id=project.id))
    
    # Add user to project members
    project.members.append(current_user)
    
    # Add user to default chat
    default_chat = Chat.query.filter_by(project_id=project.id).first()
    if default_chat:
        default_chat.members.append(current_user)
    
    # Create notification for project admins
    for admin in project.admins:
        if admin.id != current_user.id:
            notification = Notification(
                user_id=admin.id,
                sender_id=current_user.id,
                notification_type='info',
                info_type='join_project',
                text=f"{current_user.username} has joined your project: {project.title}"
            )
            db.session.add(notification)
    
    db.session.commit()
    flash('You have joined the project!')
    return redirect(url_for('projects.view', id=project.id))

@projects_bp.route('/<int:id>/leave')
@login_required
def leave(id):
    project = Project.query.get_or_404(id)
    
    if current_user.id == project.creator_id:
        flash('As the creator, you cannot leave the project.')
        return redirect(url_for('projects.view', id=project.id))
    
    if current_user not in project.members:
        flash('You are not a member of this project.')
        return redirect(url_for('projects.view', id=project.id))
    
    # Remove user from project members and admins
    project.members.remove(current_user)
    if current_user in project.admins:
        project.admins.remove(current_user)
    
    # Remove user from all project chats
    for chat in project.chats:
        if current_user in chat.members:
            chat.members.remove(current_user)
    
    # Create notification for project admins
    for admin in project.admins:
        if admin.id != current_user.id:
            notification = Notification(
                user_id=admin.id,
                sender_id=current_user.id,
                notification_type='info',
                info_type='leave_project',
                text=f"{current_user.username} has left your project: {project.title}"
            )
            db.session.add(notification)
    
    db.session.commit()
    flash('You have left the project.')
    return redirect(url_for('projects.feed'))

@projects_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    project = Project.query.get_or_404(id)

    # Authorization: Only project creator or admins can edit
    if current_user != project.creator and current_user not in project.admins:
        flash('You are not authorized to edit this project.')
        return redirect(url_for('projects.view', id=project.id))

    form = EditProjectForm(original_title=project.title)

    if form.validate_on_submit():
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

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import current_user, login_required
from app import db, limiter, socketio
from app.models import Project, User, Chat, Notification, chat_members
from app.forms import ProjectForm, SearchForm, EditProjectForm
from app.utils import load_tags
from datetime import datetime, time, timedelta
from sqlalchemy import or_, and_, func
from werkzeug.utils import secure_filename
import os
import uuid

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')

VALID_PROJECT_TYPES = ["Project", "Experiment", "Study", "Other"]

def project_match_score(user, project):
    # Count matching tags between user and project
    user_tags = set(user.skills or []) | set(user.fields_interests or [])
    project_tags = set(project.tags or [])
    return len(user_tags & project_tags)

def combine_date_time(date_obj, time_obj):
    if date_obj and time_obj:
        return datetime.combine(date_obj, time_obj)
    elif date_obj: # If only date is provided, set time to end of day (23:59:59) or start (00:00:00)
        return datetime.combine(date_obj, time.min) # Or time.max for end of day
    elif time_obj: # If only time is provided, set date to 100 years from now
        date_100_years_later = datetime.now().date() + timedelta(days=365 * 100)
        return datetime.combine(date_100_years_later, time_obj)
    else:
        # If neither date nor time is provided, return a date 100 years from now with time set to 00:00:00
        return datetime.now() + timedelta(days=365 * 100)

@projects_bp.route('/feed')
@login_required
def feed():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Get all public projects except those user is already a member of
    projects = Project.query.filter(
        Project.is_public == True,
        ~Project.members.any(User.id == current_user.id)
    ).all()

    applied_notifications = Notification.query.filter_by(
        sender_id=current_user.id,
        notification_type='invite',
        invite_type='project_application',
        status='not_answered'
    ).all()
    user_applied_project_ids = {n.project_id for n in applied_notifications if n.project_id}
    user_applied_projects = [p for p in projects if p.id in user_applied_project_ids]

    # Score and sort projects by tag match, then by image presence, then by recency
    scored_projects = []
    for project in projects:
        score = project_match_score(current_user, project)
        has_image = bool(project.image)
        scored_projects.append((score, has_image, project.created_at, project))

    # Sort: highest score first, then projects with images, then newest
    scored_projects.sort(key=lambda x: (-x[0], -x[1], -x[2].timestamp()))

    # Pagination
    total = len(scored_projects)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_projects = [p[-1] for p in scored_projects[start:end]]

    # For navigation
    has_prev = page > 1
    has_next = end < total

    return render_template('projects/feed_tinder.html',
                           projects=paginated_projects,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next,
                           total=total,
                           user_applied_projects=user_applied_projects)

@projects_bp.route('/feed_ajax')
@login_required
def feed_ajax():
    # Get offset and limit from query params
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 5, type=int)

    # Get all public projects except those user is already a member of
    projects = Project.query.filter(
        Project.is_public == True,
        ~Project.members.any(User.id == current_user.id)
    ).all()

    # Score and sort as before
    scored_projects = []
    for project in projects:
        score = project_match_score(current_user, project)
        has_image = bool(project.image)
        scored_projects.append((score, has_image, project.created_at, project))

    scored_projects.sort(key=lambda x: (-x[0], -x[1], -x[2].timestamp()))
    total = len(scored_projects)
    paginated_projects = [p[-1] for p in scored_projects[offset:offset+limit]]

    # Prepare JSON
    result = []
    for project in paginated_projects:
        result.append({
            'id': project.id,
            'title': project.title,
            'description': project.description,
            'goals': project.goals,
            'tags': project.tags,
            'creator': {
                'id': project.creator.id,
                'username': project.creator.username
            },
            'deadline': project.deadline.strftime('%d/%m/%Y') if project.deadline else None,
            'image': url_for('static', filename='uploads/' + project.image) if project.image else None,
            'apply_url': url_for('projects.apply', id=project.id),
            'view_url': url_for('projects.view', id=project.id)
        })
    return jsonify({
        'projects': result,
        'total': total
    })

@projects_bp.route('/create', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour")
def create():
    tags = load_tags()
    form = ProjectForm()
    form.tags.choices = [(tag, tag) for tag in tags['skills'] + tags['fields']]
    if form.validate_on_submit():
        allowed_tags = set(tag for tag, _ in form.tags.choices)
        if not set(form.tags.data).issubset(allowed_tags):
            flash("Invalid tag selection.")
            return render_template('projects/create.html', title='Create Project', form=form)

        project_type_data = form.project_type.data
        if project_type_data not in VALID_PROJECT_TYPES:
            project_type_data = "Other"
        
        combined_deadline = combine_date_time(form.deadline_date.data, form.deadline_time.data)
        if not combined_deadline:
            flash("Invalid deadline date provided.")
            # It's unlikely to reach here if DateField has DataRequired, but good for safety
            return render_template('projects/create.html', title='Create Project', form=form)
        
        image_filename = ""
        if form.image.data:
            filename = secure_filename(f"{uuid.uuid4()}_{form.image.data.filename}")
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            form.image.data.save(filepath)
            image_filename += filename
        
        project = Project(
            title=form.title.data,
            description=form.description.data,
            goals=form.goals.data,
            tags=form.tags.data,
            image=image_filename,
            creator_id=current_user.id,
            deadline=combined_deadline,
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
    
    tags = load_tags()
    form = EditProjectForm(original_title=project.title)
    form.tags.choices = [(tag, tag) for tag in tags['skills'] + tags['fields']]

    if form.validate_on_submit():
        allowed_tags = set(tag for tag, _ in form.tags.choices)
        if not set(form.tags.data).issubset(allowed_tags):
            flash("Invalid tag selection.")
            return render_template(f'projects/{project.id}/edit.html', title='Edit Project', form=form, project=project)
        
        project_type_data = form.project_type.data
        if project_type_data not in VALID_PROJECT_TYPES:
            project_type_data = "Other"
        
        combined_deadline = combine_date_time(form.deadline_date.data, form.deadline_time.data)
        if not combined_deadline:
            flash("Invalid deadline date provided.")
            return render_template('projects/edit_project.html', title='Edit Project', form=form, project=project)
        
        image_filename = ""
        if form.image.data:
            filename = secure_filename(f"{uuid.uuid4()}_{form.image.data.filename}")
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            form.image.data.save(filepath)
            image_filename += filename
        
        project.title = form.title.data
        project.description = form.description.data
        project.goals = form.goals.data
        project.tags = form.tags.data
        project.image = image_filename
        project.deadline = combined_deadline
        project.project_type = form.project_type.data
        project.is_public = form.is_public.data
        db.session.commit()
        flash('Your project has been updated!')
        return redirect(url_for('projects.view', id=project.id))
    elif request.method == 'GET':
        form.title.data = project.title
        form.description.data = project.description
        form.goals.data = project.goals
        form.tags.data = project.tags or []
        if project.deadline:
            form.deadline_date.data = project.deadline.date()
            # Only set time if it's not midnight (or your default)
            if project.deadline.time() != time.min:
                form.deadline_time.data = project.deadline.time()
        form.project_type.data = project.project_type
        form.is_public.data = project.is_public

    return render_template('projects/edit_project.html', title='Edit Project',
                           form=form, project=project)

@projects_bp.route('/search_ajax') # Endpoint for live search dropdown
@login_required
def search_ajax():
    query = request.args.get('query', '').strip()
    
    if not query or len(query) < 2: # Minimum characters to trigger search
        return jsonify([]) # Return empty list if query is too short

    results_limit = 5 # Max number of items per category in dropdown

    # Search public projects (title, description, goals)
    project_results = Project.query.filter(
        Project.is_public == True,
        or_(
            Project.title.ilike(f'%{query}%'),
            Project.description.ilike(f'%{query}%'),
            Project.goals.ilike(f'%{query}%')
        )
    ).order_by(Project.title).limit(results_limit).all() # Order for some consistency

    # Search chats user is a member of (name)
    chat_results = Chat.query.join(
        chat_members # The association table
    ).filter(
        chat_members.c.user_id == current_user.id, # Filter by current user's membership
        Chat.name.ilike(f'%{query}%')
    ).order_by(Chat.name).limit(results_limit).all() # Order for some consistency

    # Format results for the dropdown
    formatted_results = []

    for p in project_results:
        formatted_results.append({
            'id': p.id,
            'title': p.title,
            # 'description': (p.description[:75] + '...') if p.description and len(p.description) > 75 else p.description,
            'type': 'project',
            'url': url_for('projects.view', id=p.id)
        })

    for c in chat_results:
        formatted_results.append({
            'id': c.id,
            'name': c.name,
            'project_title': c.project.title if c.project else 'N/A', # Context for chat
            'type': 'chat',
            'url': url_for('chats.view', id=c.id)
        })
    
    # formatted_results.sort(key=lambda x: x.get('title', x.get('name', '')).lower())
    return jsonify(formatted_results)

@projects_bp.route('/search') # Full search results page
@login_required
def search_results_page():
    query = request.args.get('query', '').strip()
    # If query is empty, maybe redirect to feed or show a message
    if not query:
        flash("Please enter a search term.")
        return redirect(request.referrer or url_for('projects.feed'))


    page = request.args.get('page', 1, type=int)
    per_page = 10 

    # Query for projects
    project_query_obj = Project.query.filter(
        Project.is_public == True,
        or_(
            Project.title.ilike(f'%{query}%'),
            Project.description.ilike(f'%{query}%'),
            Project.goals.ilike(f'%{query}%')
        )
    )
    projects_paginated = project_query_obj.order_by(Project.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Query for chats
    # For the full search page, we might want to paginate chats independently or combine differently.
    # The previous implementation paginated them separately. Let's stick to that for now.
    chat_query_obj = Chat.query.join(chat_members).filter(
        chat_members.c.user_id == current_user.id,
        Chat.name.ilike(f'%{query}%')
    )
    # If you want chats to have their own pagination on the search results page:
    # chat_page = request.args.get('chat_page', 1, type=int) # Separate page param for chats
    # chats_paginated = chat_query_obj.order_by(Chat.created_at.desc()).paginate(page=chat_page, per_page=per_page, error_out=False)
    # For simplicity, let's assume for now the main 'page' param applies to both, or show all matching chats.
    # Or, just show a limited number of chats on the main search results page if not paginating them separately.
    
    # For this example, let's paginate chats as well, using the same page number.
    # This means if page=2 for projects, it's also page=2 for chats.
    chats_paginated = chat_query_obj.order_by(Chat.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


    current_app.logger.debug(f"Full Search for '{query}' by user {current_user.id}. Projects found: {projects_paginated.total}, Chats found: {chats_paginated.total}")

    return render_template('projects/search_results.html', 
                           title=f"Search Results for '{query}'",
                           query=query,
                           projects=projects_paginated,
                           chats=chats_paginated)

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

@projects_bp.route('/<int:id>/delete', methods=['POST']) # POST to prevent accidental deletion via GET
@login_required
def delete_project(id):
    project = Project.query.get_or_404(id)

    # Authorization: Only project creator can delete
    if current_user.id != project.creator_id:
        flash('You are not authorized to delete this project. Only the creator can.')
        return redirect(url_for('projects.view', id=project.id))

    try:
        # Delete associated notifications (optional, or handle via cascade)
        Notification.query.filter_by(project_id=project.id).delete()
        
        # Chats are set to cascade delete via SQLAlchemy relationship,
        # but messages within those chats might need explicit handling if not cascaded from chat.
        # Assuming Message.chat_id has ondelete='CASCADE' or similar, or handled by chat cascade.
        # If not, you'd loop through project.chats and delete messages first.

        db.session.delete(project)
        db.session.commit()
        flash(f"Project '{project.title}' and all its associated chats and data have been deleted.")
        return redirect(url_for('projects.feed'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting project {id}: {str(e)}", exc_info=True)
        flash("An error occurred while trying to delete the project. Please try again.")
        return redirect(url_for('projects.view', id=project.id))

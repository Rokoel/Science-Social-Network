from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from app import db, limiter
from app.models import User
from app.forms import EditProfileForm
import os
import json
from werkzeug.utils import secure_filename
import uuid

users_bp = Blueprint('users', __name__, url_prefix='/users')

@users_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = EditProfileForm(current_user.username, current_user.email)
    
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.name = form.name.data
        current_user.surname = form.surname.data
        current_user.family_name = form.family_name.data
        current_user.skills = form.skills.data
        current_user.university = form.university.data
        current_user.degree = form.degree.data
        current_user.fields_interests = form.fields_interests.data
        
        # Handle avatar upload
        if form.avatar.data:
            filename = secure_filename(f"{uuid.uuid4()}_{form.avatar.data.filename}")
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            form.avatar.data.save(filepath)
            current_user.avatar = filename
        
        db.session.commit()
        flash('Your profile has been updated!')
        return redirect(url_for('users.profile'))
    
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.name.data = current_user.name
        form.surname.data = current_user.surname
        form.family_name.data = current_user.family_name
        form.skills.data = current_user.skills
        form.university.data = current_user.university
        form.degree.data = current_user.degree
        form.fields_interests.data = current_user.fields_interests
    
    # Load achievements
    achievements = []
    if current_user.achievements:
        achievement_ids = json.loads(current_user.achievements)
        
        try:
            with open(current_app.config['ACHIEVEMENTS_FILE'], 'r') as f:
                all_achievements = json.load(f)
                
            for achievement_id in achievement_ids:
                achievement = next((a for a in all_achievements if a.get('id') == achievement_id), None)
                if achievement:
                    achievements.append(achievement)
        except (json.JSONDecodeError, FileNotFoundError):
            flash('Error loading achievements')
    
    return render_template('users/profile.html', 
                          title='Profile',
                          form=form,
                          achievements=achievements)

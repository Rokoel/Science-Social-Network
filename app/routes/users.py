from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import current_user, login_required
from app import db, limiter
from app.models import User, Project, Chat
from app.forms import EditProfileForm
from app.utils import load_tags
import os
import json
from werkzeug.utils import secure_filename
import uuid

users_bp = Blueprint('users', __name__, url_prefix='/users')

@users_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    tags = load_tags()
    form = EditProfileForm(current_user.username, current_user.email)
    form.skills.choices = [(tag, tag) for tag in tags['skills']]
    form.fields_interests.choices = [(tag, tag) for tag in tags['fields']]

    if form.validate_on_submit():
        allowed_skills = set(tag for tag, _ in form.skills.choices)
        allowed_fields = set(tag for tag, _ in form.fields_interests.choices)
        if not set(form.skills.data).issubset(allowed_skills) or not set(form.fields_interests.data).issubset(allowed_fields):
            flash("Invalid tag selection.")
            return render_template('users/profile.html', title='Profile', form=form)
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.name = form.name.data
        current_user.surname = form.surname.data
        current_user.family_name = form.family_name.data
        current_user.university = form.university.data
        current_user.degree = form.degree.data
        current_user.skills = form.skills.data
        current_user.fields_interests = form.fields_interests.data

        if form.avatar.data:
            if current_user.avatar and current_user.avatar != "default.jpg":
                try:
                    os.remove(
                        os.path.join(
                            current_app.config["UPLOAD_FOLDER"],
                            current_user.avatar,
                        )
                    )
                except OSError:
                    pass  # File might not exist, or other error
            filename = secure_filename(
                f"{uuid.uuid4()}_{form.avatar.data.filename}"
            )
            filepath = os.path.join(
                current_app.config["UPLOAD_FOLDER"], filename
            )
            form.avatar.data.save(filepath)
            current_user.avatar = filename

        db.session.commit()
        flash("Your profile has been updated!")
        return redirect(url_for("users.profile"))

    elif request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.name.data = current_user.name
        form.surname.data = current_user.surname
        form.family_name.data = current_user.family_name
        form.skills.data = current_user.skills
        form.university.data = current_user.university
        form.degree.data = current_user.degree
        form.fields_interests.data = current_user.fields_interests

    achievements = []
    if current_user.achievements:
        try:
            achievement_ids = json.loads(current_user.achievements)
            if achievement_ids: # Ensure it's not an empty list string causing error
                with open(current_app.config["ACHIEVEMENTS_FILE"], "r") as f:
                    all_achievements = json.load(f)
                for achievement_id in achievement_ids:
                    achievement = next(
                        (
                            a
                            for a in all_achievements
                            if a.get("id") == achievement_id
                        ),
                        None,
                    )
                    if achievement:
                        achievements.append(achievement)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            current_app.logger.error(f"Error loading achievements: {e}")
            flash("Error loading achievements for your profile.")
        except TypeError: # If json.loads results in None or non-iterable
            current_app.logger.error(f"Error processing achievements: {current_user.achievements}")


    return render_template(
        "users/profile.html",
        title="Profile",
        form=form,
        achievements=achievements,
        user_to_display=current_user # Pass user explicitly
    )


@users_bp.route("/view/<int:user_id>")
@login_required
def view_profile(user_id):
    user_to_display = User.query.get_or_404(user_id)
    if user_to_display == current_user:
        return redirect(url_for("users.profile"))

    achievements = []
    if user_to_display.achievements:
        try:
            achievement_ids = json.loads(user_to_display.achievements)
            if achievement_ids:
                with open(current_app.config["ACHIEVEMENTS_FILE"], "r") as f:
                    all_achievements = json.load(f)
                for achievement_id in achievement_ids:
                    achievement = next(
                        (
                            a
                            for a in all_achievements
                            if a.get("id") == achievement_id
                        ),
                        None,
                    )
                    if achievement:
                        achievements.append(achievement)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            current_app.logger.error(f"Error loading achievements for user {user_id}: {e}")
        except TypeError:
             current_app.logger.error(f"Error processing achievements for user {user_id}: {user_to_display.achievements}")


    # For "Invite to Chat"
    # Find projects where current_user is admin and user_to_display is a member but not in all chats
    common_projects_admin = []
    if current_user.admin_projects:
        for project in current_user.admin_projects:
            if user_to_display in project.members:
                # Find chats in this project where current_user is admin (implied by project admin)
                # and user_to_display is not yet a member
                eligible_chats = [
                    chat for chat in project.chats 
                    if user_to_display not in chat.members and current_user in project.admins # current_user is project admin
                ]
                if eligible_chats:
                    common_projects_admin.append({
                        'project': project,
                        'eligible_chats': eligible_chats
                    })


    return render_template(
        "users/profile_view.html",
        title=f"{user_to_display.username}'s Profile",
        user_to_display=user_to_display,
        achievements=achievements,
        common_projects_admin=common_projects_admin
    )
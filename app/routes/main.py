from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    # Redirect to projects feed if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('projects.feed'))
    
    # Otherwise, show the landing page
    return render_template('index.html')

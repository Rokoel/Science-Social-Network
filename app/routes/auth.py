from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db, limiter
from app.models import User
from app.forms import LoginForm, RegistrationForm
import json
from flask import jsonify
from flask import current_app
import requests

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('projects.feed'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password', 'error')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('projects.feed')
        return redirect(next_page)
    
    return render_template('auth/login.html', title='Sign In', form=form,
                           vk_app_id_for_sdk=current_app.config['VK_APP_ID'],
                           vk_redirect_uri_for_sdk=current_app.config['VK_REDIRECT_URI_FOR_SDK'],
                           current_app=current_app)

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('projects.feed'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            name=form.name.data,
            surname=form.surname.data,
            achievements=json.dumps([])
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now registered!', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', title='Register', form=form)


@auth_bp.route('/auth/vk/sdk_token_login', methods=['POST'])
@limiter.limit("10 per minute")
def vk_sdk_token_login():
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': 'No data received.'}), 400

    access_token = data.get('access_token')
    vk_user_id_from_token = data.get('user_id') # The SDK provides user_id directly in the success payload

    current_app.logger.info(f"Received VK SDK token login attempt. Access token present: {bool(access_token)}, VK User ID: {vk_user_id_from_token}")

    if not access_token or not vk_user_id_from_token:
        return jsonify({'success': False, 'message': 'Missing access token or VK user ID.'}), 400

    # 1. OPTIONAL BUT RECOMMENDED: Verify token by fetching user info from VK API
    # This confirms the access token is valid and belongs to the claimed user_id.
    user_info_url = 'https://id.vk.com/oauth2/user_info'
    user_info_headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        user_info_response = requests.get(user_info_url, headers=user_info_headers)
        user_info_response.raise_for_status() # Raise an exception for HTTP errors
        vk_user_data_full = user_info_response.json()
        vk_user_data = vk_user_data_full.get('user')
        current_app.logger.debug(f"VK User Info from token verification: {vk_user_data}")

        if not vk_user_data or str(vk_user_data.get('user_id')) != str(vk_user_id_from_token):
            current_app.logger.warning(f"VK token verification failed: User ID mismatch or no user data. SDK UserID: {vk_user_id_from_token}, API UserID: {vk_user_data.get('user_id') if vk_user_data else 'N/A'}")
            return jsonify({'success': False, 'message': 'Invalid VK token or user ID mismatch.'}), 401
            
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"VK User Info HTTP error during token verification: {str(e)}. Response: {user_info_response.text if 'user_info_response' in locals() else 'N/A'}")
        return jsonify({'success': False, 'message': f'Error verifying VK token: {str(e)}'}), 500
    except ValueError: # Includes JSONDecodeError
        current_app.logger.error(f"VK User Info JSON parsing error during token verification. Response: {user_info_response.text}")
        return jsonify({'success': False, 'message': 'Error parsing VK user info for verification.'}), 500

    # 2. Login or Register User in Your System
    vk_id_str = str(vk_user_id_from_token)
    user = User.query.filter_by(vk_id=vk_id_str).first()

    if user: # Existing user
        login_user(user, remember=True)
        current_app.logger.info(f"Existing user {user.username} (VK ID: {vk_id_str}) logged in via SDK token.")
        return jsonify({'success': True, 'redirect_url': url_for('projects.feed')})
    else: # New user
        vk_email = vk_user_data.get('email')
        if vk_email:
            existing_email_user = User.query.filter_by(email=vk_email, vk_id=None).first()
            if existing_email_user:
                current_app.logger.warning(f"VK SDK new user: Email {vk_email} already exists for a non-VK account.")
                return jsonify({'success': False, 'message': f"An account with email {vk_email} already exists. Please log in with your password."})
        
        base_username = vk_user_data.get('first_name', 'vk_user').lower().replace(' ', '_')
        username_candidate = base_username
        counter = 1
        while User.query.filter_by(username=username_candidate).first():
            username_candidate = f"{base_username}{counter}"
            counter += 1
        
        new_user = User(
            vk_id=vk_id_str,
            username=username_candidate,
            email=vk_email,
            name=vk_user_data.get('first_name'),
            surname=vk_user_data.get('last_name'),
            # avatar=vk_user_data.get('avatar'), # Download and save avatar
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user, remember=True)
        current_app.logger.info(f"New user {new_user.username} (VK ID: {vk_id_str}) created and logged in via SDK token.")
        return jsonify({'success': True, 'message': 'Successfully registered and logged in with VK ID!', 'redirect_url': url_for('projects.feed')})

# Minimal callback for SDK if it still uses redirectUrl for something (e.g., closing a popup)
@auth_bp.route('/auth/vk/sdk_helper')
def vk_sdk_helper():
    # This page might just close itself if opened in a popup by the SDK,
    # or display a generic "Please wait..." message.
    # The main logic is handled client-side by the LOGIN_SUCCESS event.
    current_app.logger.info("VK SDK Helper Callback Reached. Payload: " + str(request.args.get('payload')))
    # You might get a payload here too, but the LOGIN_SUCCESS event is primary for this SDK flow.
    return "<script>window.close();</script>Please wait, processing VK login..."
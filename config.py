import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configurations
    # Resolved against the instance directory by create_app; never serve as static.
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB limit
    
    # Redis config
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Session config
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Achievements path
    ACHIEVEMENTS_FILE = 'achievements.json'

    VK_APP_ID = os.environ.get('VK_APP_ID') or '53619900'
    VK_SECURE_KEY = os.environ.get('VK_SECURE_KEY') or 'YOUR_VK_SECURE_KEY'
    # This MUST match exactly what you registered in the VK App settings
    VK_REDIRECT_URI = os.environ.get('VK_REDIRECT_URI') or 'https://thisisamoguswebsite.org/auth/vk/callback'
    VK_REDIRECT_URI_FOR_SDK = VK_REDIRECT_URI
    VK_SCOPE = "email"

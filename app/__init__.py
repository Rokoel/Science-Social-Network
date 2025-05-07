# In app/__init__.py
import os
from flask import Flask
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from datetime import datetime

# Initialize extensions
db = SQLAlchemy()
socketio = SocketIO()
login_manager = LoginManager()
csrf = CSRFProtect()
redis_client = None
limiter = Limiter(key_func=get_remote_address,
                  storage_uri="redis://localhost:6379")

def create_app(config_class='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize Redis client
    global redis_client
    redis_url = app.config['REDIS_URL']
    redis_client = redis.from_url(redis_url)
    
    # Initialize extensions with app
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    
    # Set login view
    login_manager.login_view = 'auth.login'
    
    # Configure limiter with storage and app
    limiter.storage_uri = redis_url
    limiter.init_app(app)
    
    # Initialize SocketIO
    socketio.init_app(app, message_queue=redis_url, cors_allowed_origins="*")
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}
    
    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.projects import projects_bp
    from app.routes.users import users_bp
    from app.routes.chats import chats_bp
    from app.routes.notifications import notifications_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(chats_bp)
    app.register_blueprint(notifications_bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app

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
import logging

# Initialize extensions
db = SQLAlchemy()
socketio = SocketIO()
login_manager = LoginManager()
csrf = CSRFProtect()
redis_client = None
limiter = Limiter(key_func=get_remote_address)

def create_app(config_class='config.Config', use_redis=True):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.debug:
        logging.basicConfig(level=logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        app.logger.setLevel(logging.INFO)
    
    global redis_client

    if use_redis:
        redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379')
        redis_client = redis.from_url(redis_url)
        limiter._storage_uri = redis_url
        socketio_kwargs = {
            'message_queue': redis_url,
            'cors_allowed_origins': "*",
            'max_http_buffer_size': 10 * 1024 * 1024
        }
    else:
        redis_client = None
        limiter._storage_uri = None  # Use in-memory storage
        socketio_kwargs = {
            'cors_allowed_origins': "*",
            'max_http_buffer_size': 10 * 1024 * 1024
        }
    
    # Initialize extensions with app
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    limiter.init_app(app)
    socketio.init_app(app, **socketio_kwargs)
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, 'achievements_icons'), exist_ok=True)

    from app.utils import nl2br
    app.jinja_env.filters['nl2br'] = nl2br

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

    from . import sockets

    with app.app_context():
        db.create_all()

    return app

"""Shared isolated Flask fixtures. No live database, Redis, or network is used."""

import re
import tempfile
import unittest
from pathlib import Path
from flask_migrate import upgrade

from app import create_app, db
from app.models import Chat, Message, Project, ProjectMaterial, User
from config import Config


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)

        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = 'test-secret'
            SQLALCHEMY_DATABASE_URI = 'sqlite://'
            UPLOAD_FOLDER = str(root / 'private-uploads')
            RATELIMIT_ENABLED = False

        self.app = create_app(TestConfig, use_redis=False)
        self.app.static_folder = str(root / 'static')
        self.legacy = root / 'static' / 'uploads'
        self.legacy.mkdir(parents=True)
        self.uploads = Path(self.app.config['UPLOAD_FOLDER'])
        self.client = self.app.test_client()
        with self.app.app_context():
            upgrade()
            owner = User(username='owner', email='owner@example.com')
            outsider = User(username='outsider', email='outsider@example.com')
            project = Project(title='Private project', creator=owner, is_public=False)
            project.members.append(owner)
            project.admins.append(owner)
            chat = Chat(name='Private chat', creator=owner, project=project)
            chat.members.append(owner)
            message = Message(text='Private message', author=owner, chat=chat, file='attachment.txt')
            material = ProjectMaterial(project=project, uploaded_by=owner,
                                       filename='material.txt', original_name='research.txt')
            db.session.add_all([owner, outsider, project, chat, message, material])
            db.session.commit()
            self.owner_id, self.outsider_id = owner.id, outsider.id
            self.project_id, self.chat_id = project.id, chat.id
            self.message_id, self.material_id = message.id, material.id
        self.addCleanup(self.cleanup_database)

    def cleanup_database(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user_id)
            session['_fresh'] = True

    def get(self, route, **kwargs):
        response = self.client.get(route, **kwargs)
        self.addCleanup(response.close)
        return response

    def csrf_token(self):
        page = self.get('/login', follow_redirects=True).get_data(as_text=True)
        return re.search(r'<meta name="csrf-token" content="([^"]+)"', page)[1]

    def post(self, route, data=None):
        return self.client.post(route, data=data, headers={'X-CSRFToken': self.csrf_token()})

    def add_member(self, user_id, *, admin=False, chat=True):
        with self.app.app_context():
            user = db.session.get(User, user_id)
            project = db.session.get(Project, self.project_id)
            if user not in project.members:
                project.members.append(user)
            if admin and user not in project.admins:
                project.admins.append(user)
            room = db.session.get(Chat, self.chat_id)
            if chat and user not in room.members:
                room.members.append(user)
            db.session.commit()

    def create_project(self, **overrides):
        """Exercise project creation through the form, including its default chat."""
        self.login(self.owner_id)
        response = self.post('/projects/create', {
            'title': 'Research project', 'description': 'Research description',
            'goals': 'Reproduce an experiment', 'project_type': 'Project',
            'is_public': 'y', **overrides,
        })
        self.assertEqual(response.status_code, 302)
        return int(response.location.rsplit('/', 1)[1])


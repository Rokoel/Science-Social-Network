from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import PickleType

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Association tables for many-to-many relationships
project_members = db.Table('project_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'))
)

project_admins = db.Table('project_admins',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'))
)

chat_members = db.Table('chat_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('chat_id', db.Integer, db.ForeignKey('chat.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(64))
    surname = db.Column(db.String(64))
    family_name = db.Column(db.String(64))
    university = db.Column(db.String(120))
    degree = db.Column(db.String(64))
    skills = db.Column(MutableList.as_mutable(PickleType), default=[])
    fields_interests = db.Column(MutableList.as_mutable(PickleType), default=[])
    avatar = db.Column(db.String(120), default='default-avatar.svg')
    achievements = db.Column(db.Text, default='[]')  # Store as JSON string of achievement IDs
    
    # Relationships
    created_projects = db.relationship('Project', backref='creator', lazy='dynamic', 
                                       foreign_keys='Project.creator_id')
    created_chats = db.relationship('Chat', backref='creator', lazy='dynamic',
                                    foreign_keys='Chat.creator_id')
    messages = db.relationship('Message', backref='author', lazy='dynamic')
    sent_notifications = db.relationship('Notification', backref='sender', lazy='dynamic',
                                        foreign_keys='Notification.sender_id')
    received_notifications = db.relationship('Notification', backref='recipient', lazy='dynamic',
                                           foreign_keys='Notification.user_id')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def add_achievement(self, achievement_id):
        achievements = json.loads(self.achievements)
        if achievement_id not in achievements:
            achievements.append(achievement_id)
            self.achievements = json.dumps(achievements)
            return True
        return False
        
    def remove_achievement(self, achievement_id):
        achievements = json.loads(self.achievements)
        if achievement_id in achievements:
            achievements.remove(achievement_id)
            self.achievements = json.dumps(achievements)
            return True
        return False
        
    def __repr__(self):
        return f'<User {self.username}>'

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), index=True)
    description = db.Column(db.Text)
    goals = db.Column(db.Text)
    tags = db.Column(MutableList.as_mutable(PickleType), default=[])
    image = db.Column(db.String(120))
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime)
    project_type = db.Column(db.String(50))
    is_public = db.Column(db.Boolean, default=True)
    
    # Relationships
    members = db.relationship('User', secondary=project_members, 
                             backref=db.backref('projects', lazy='dynamic'))
    admins = db.relationship('User', secondary=project_admins,
                            backref=db.backref('admin_projects', lazy='dynamic'))
    chats = db.relationship('Chat', backref='project', lazy='dynamic')
    
    def __repr__(self):
        return f'<Project {self.title}>'

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    
    # Relationships
    members = db.relationship('User', secondary=chat_members,
                             backref=db.backref('chats', lazy='dynamic'))
    messages = db.relationship('Message', backref='chat', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Chat {self.name}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'))
    file = db.Column(db.String(120))  # Path to uploaded file if any
    
    def __repr__(self):
        return f'<Message {self.id}>'

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Recipient
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.now())
    notification_type = db.Column(db.String(20))  # "info" or "invite"
    info_type = db.Column(db.String(50), nullable=True)
    invite_type = db.Column(db.String(50), nullable=True)
    text = db.Column(db.Text)
    status = db.Column(db.String(20), default='not_answered')  # accepted, rejected, not_answered
    dismissed = db.Column(db.Boolean, default=False)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    
    def __repr__(self):
        return f'<Notification {self.id}>'
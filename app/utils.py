from flask import current_app
import json
from app.models import User
from app import db
import os

def load_achievements():
    """Load all achievements from the JSON file"""
    try:
        with open(current_app.config['ACHIEVEMENTS_FILE'], 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Create default file if it doesn't exist
        achievements = [
            {
                "id": 1,
                "name": "First Project",
                "description": "Created your first project",
                "icon": "project_icon.png"
            },
            {
                "id": 2,
                "name": "Team Player",
                "description": "Joined 5 different projects",
                "icon": "team_icon.png"
            },
            {
                "id": 3,
                "name": "Communicator",
                "description": "Sent 100 messages in chats",
                "icon": "chat_icon.png"
            }
        ]
        
        save_achievements(achievements)
        return achievements

def save_achievements(achievements):
    """Save achievements to the JSON file"""
    with open(current_app.config['ACHIEVEMENTS_FILE'], 'w') as f:
        json.dump(achievements, f, indent=4)

def grant_achievement(user_id, achievement_id):
    """Grant an achievement to a user"""
    user = User.query.get(user_id)
    if not user:
        return False
    
    result = user.add_achievement(achievement_id)
    if result:
        db.session.commit()
    return result

def remove_achievement(user_id, achievement_id):
    """Remove an achievement from a user"""
    user = User.query.get(user_id)
    if not user:
        return False
    
    result = user.remove_achievement(achievement_id)
    if result:
        db.session.commit()
    return result

def check_achievement_conditions(user_id):
    """Check if a user meets conditions for achievements"""
    # This is a stub function to be expanded with actual achievement logic
    # For example, counting projects, messages, etc.
    pass

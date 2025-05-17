from flask import current_app
import json
from app.models import User
from app import db
import os
from markupsafe import Markup, escape
from jinja2 import pass_eval_context

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

@pass_eval_context
def nl2br(eval_ctx, value):
    """Converts newlines in a string to HTML line breaks."""
    br = "<br>\n"
    
    # Ensure the value is a string and escape it to prevent XSS
    value = str(escape(value))
    
    # Replace \r\n, \r, and \n with <br>
    result = value.replace('\r\n', br).replace('\r', br).replace('\n', br)
    
    if eval_ctx.autoescape:
        return Markup(result)
    return result

def load_tags():
    tags_path = os.path.join(os.path.dirname(__file__), '..', 'tags.json')
    with open(tags_path, 'r') as f:
        return json.load(f)


def secure_filename(filename: str) -> str:
    import os, re
    text_type = str
    _windows_device_files = (
        "CON",
        "AUX",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "LPT1",
        "LPT2",
        "LPT3",
        "PRN",
        "NUL",
    )
    _filename_strip_re = re.compile(r"[^A-Za-zа-яА-ЯёЁйЙ0-9_.-]")
    
    if isinstance(filename, text_type):
        from unicodedata import normalize
        filename = normalize("NFKD", filename)

    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, " ")

    filename = str(_filename_strip_re.sub("", "_".join(filename.split()))).strip("._")
    if (os.name == "nt"
        and filename
        and filename.split(".")[0].upper() in _windows_device_files):
        filename = f"_{filename}"

    return filename
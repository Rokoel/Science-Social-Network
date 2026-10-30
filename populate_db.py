import os
import json
from app import create_app, db
from app.models import User, Project
from werkzeug.security import generate_password_hash

# 1. Load sample projects from JSON
def load_sample_projects():
    with open('sample_projects.json', 'r') as f:
        return json.load(f)

# 2. Create users and projects
def populate():
    app = create_app()
    with app.app_context():
        # Run flask db upgrade first; seeding must never replace the schema.
        if User.query.first() or Project.query.first():
            raise RuntimeError('Sample data requires an empty, migrated database.')

        # Create three users
        users = [
            User(
                username='Rokoel',
                email='rokoelvel@gmail.com',
                name='Antonio',
                surname='Velasquez',
                password_hash=generate_password_hash('12345678'),
                skills=['Python', 'AI', 'Data Analysis'],
                fields_interests=['Healthcare', 'Bioinformatics']
            ),
            User(
                username='Sergey',
                email='sergey@gmail.com',
                name='Sergey',
                surname='Sergeev',
                password_hash=generate_password_hash('12345678'),
                skills=['Quantum Computing', 'Chemistry', 'Simulation'],
                fields_interests=['Physics', 'Ecology']
            ),
            User(
                username='carol',
                email='carol@example.com',
                name='Carol',
                surname='Williams',
                password_hash=generate_password_hash('password3'),
                skills=['Neuroscience', 'Biology', 'Automation'],
                fields_interests=['Neuroscience', 'Survey']
            )
        ]
        for user in users:
            db.session.add(user)
        db.session.commit()

        # Load sample projects
        sample_projects = load_sample_projects()

        # Assign 5 projects to each user as creator
        for idx, user in enumerate(users):
            for i, proj_data in enumerate(sample_projects):
                # Make a copy so tags list isn't shared
                proj = Project(
                    title=f"{proj_data['title']} ({user.username})",
                    description=proj_data['description'],
                    goals=proj_data['goals'],
                    creator_id=user.id,
                    project_type=proj_data['project_type'],
                    is_public=proj_data['is_public'],
                    tags=list(proj_data['tags']),
                    deadline=None
                )
                proj.admins.append(user)
                proj.members.append(user)
                db.session.add(proj)
        db.session.commit()

        print("Database populated with 3 users and 5 projects each.")

if __name__ == '__main__':
    populate()

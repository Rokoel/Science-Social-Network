"""Project role boundaries and membership changes, checked against persisted state."""

from app import db
from app.models import Chat, Notification, Project, User
from tests.support import AppTestCase


class ProjectPermissionTests(AppTestCase):
    def test_creation_makes_creator_admin_and_default_chat_member(self):
        project_id = self.create_project()
        with self.app.app_context():
            project = db.session.get(Project, project_id)
            self.assertEqual(project.creator_id, self.owner_id)
            self.assertEqual([user.id for user in project.members], [self.owner_id])
            self.assertEqual([user.id for user in project.admins], [self.owner_id])
            chat = project.chats.one()
            self.assertEqual(chat.name, f'{project.title} Chat')
            self.assertEqual([user.id for user in chat.members], [self.owner_id])

    def test_private_project_is_visible_only_to_members(self):
        self.login(self.outsider_id)
        response = self.get(f'/projects/{self.project_id}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/projects/feed')
        self.add_member(self.outsider_id)
        self.assertEqual(self.get(f'/projects/{self.project_id}').status_code, 200)

    def test_member_cannot_edit_delete_or_promote_themselves(self):
        self.add_member(self.outsider_id)
        self.login(self.outsider_id)
        mutations = [
            (f'/projects/{self.project_id}/edit', {'title': 'Unauthorized edit'}),
            (f'/projects/{self.project_id}/delete', None),
            (f'/projects/{self.project_id}/manage_member/{self.outsider_id}/make_admin', None),
        ]
        self.assertEqual(self.get(f'/projects/{self.project_id}/edit').status_code, 302)
        for route, data in mutations:
            with self.subTest(route=route):
                self.assertEqual(self.post(route, data).status_code, 302)
                with self.app.app_context():
                    project = db.session.get(Project, self.project_id)
                    self.assertIsNotNone(project)
                    self.assertEqual(project.title, 'Private project')
                    self.assertEqual([user.id for user in project.admins], [self.owner_id])
                    self.assertEqual(Notification.query.count(), 0)

    def test_admin_can_edit_but_cannot_delete_project(self):
        self.add_member(self.outsider_id, admin=True)
        self.login(self.outsider_id)
        self.assertEqual(self.get(f'/projects/{self.project_id}/edit').status_code, 200)
        response = self.post(f'/projects/{self.project_id}/edit', {
            'title': 'Edited by admin', 'description': 'Updated description',
            'goals': 'Updated goals', 'project_type': 'Project',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.post(f'/projects/{self.project_id}/delete').status_code, 302)
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertIsNotNone(project)
            self.assertEqual(project.title, 'Edited by admin')

    def test_admin_cannot_remove_or_demote_creator(self):
        self.add_member(self.outsider_id, admin=True)
        self.login(self.outsider_id)
        for action in ['remove_member', 'remove_admin']:
            with self.subTest(action=action):
                response = self.post(f'/projects/{self.project_id}/manage_member/{self.owner_id}/{action}')
                self.assertEqual(response.status_code, 302)
                with self.app.app_context():
                    project = db.session.get(Project, self.project_id)
                    owner = db.session.get(User, self.owner_id)
                    self.assertEqual(project.creator_id, self.owner_id)
                    self.assertIn(owner, project.members)
                    self.assertIn(owner, project.admins)
                    self.assertIn(owner, db.session.get(Chat, self.chat_id).members)
                    self.assertEqual(Notification.query.count(), 0)

    def test_owner_can_promote_and_demote_a_member(self):
        self.add_member(self.outsider_id)
        self.login(self.owner_id)
        for action, expected in [('make_admin', True), ('remove_admin', False)]:
            with self.subTest(action=action):
                self.assertEqual(self.post(f'/projects/{self.project_id}/manage_member/{self.outsider_id}/{action}').status_code, 302)
                with self.app.app_context():
                    project = db.session.get(Project, self.project_id)
                    member = db.session.get(User, self.outsider_id)
                    self.assertEqual(member in project.admins, expected)
                    self.assertIn(member, project.members)

    def test_removal_clears_membership_admin_role_and_all_project_chats(self):
        self.add_member(self.outsider_id, admin=True)
        with self.app.app_context():
            extra = Chat(name='Second chat', project_id=self.project_id, creator_id=self.owner_id)
            extra.members.append(db.session.get(User, self.outsider_id))
            db.session.add(extra)
            db.session.commit()
        self.login(self.owner_id)
        response = self.post(f'/projects/{self.project_id}/manage_member/{self.outsider_id}/remove_member')
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            member = db.session.get(User, self.outsider_id)
            self.assertNotIn(member, project.members)
            self.assertNotIn(member, project.admins)
            for chat in project.chats:
                self.assertNotIn(member, chat.members)
            notice = Notification.query.filter_by(user_id=self.outsider_id, info_type='removed_from_project').one()
            self.assertEqual(notice.project_id, self.project_id)
        self.login(self.outsider_id)
        self.assertEqual(self.get(f'/projects/{self.project_id}').status_code, 302)
        self.assertEqual(self.get(f'/chats/{self.chat_id}').status_code, 302)

    def test_sole_creator_cannot_leave_or_remove_themselves(self):
        self.login(self.owner_id)
        for route in [f'/projects/{self.project_id}/leave',
                      f'/projects/{self.project_id}/manage_member/{self.owner_id}/remove_member']:
            self.assertEqual(self.post(route).status_code, 302)
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            self.assertEqual([user.id for user in project.members], [self.owner_id])
            self.assertEqual([user.id for user in project.admins], [self.owner_id])

    def test_private_project_rejects_applications(self):
        self.login(self.outsider_id)
        self.assertEqual(self.post(f'/projects/{self.project_id}/apply').status_code, 302)
        with self.app.app_context():
            self.assertEqual(Notification.query.count(), 0)
            self.assertEqual([user.id for user in db.session.get(Project, self.project_id).members], [self.owner_id])

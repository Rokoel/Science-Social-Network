"""Applications and invitations exercised through the HTTP endpoints."""

from app import db
from app.models import Chat, Notification, Project, User, chat_members, project_members
from tests.support import AppTestCase


class ApplicationTests(AppTestCase):
    def apply_to_project(self, project_id):
        self.login(self.outsider_id)
        response = self.post(f'/projects/{project_id}/apply')
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            return Notification.query.filter_by(
                project_id=project_id, sender_id=self.outsider_id,
                invite_type='project_application',
            ).one().id

    def test_accepted_applicant_joins_the_chat_created_with_project(self):
        project_id = self.create_project()
        with self.app.app_context():
            default_chat_id = Chat.query.filter_by(project_id=project_id).one().id
            extra = Chat(name='Separate discussion', project_id=project_id, creator_id=self.owner_id)
            db.session.add(extra)
            db.session.commit()
            extra_chat_id = extra.id
        application_id = self.apply_to_project(project_id)
        self.login(self.owner_id)
        response = self.post(f'/notifications/{application_id}/accept')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        with self.app.app_context():
            applicant = db.session.get(User, self.outsider_id)
            self.assertIn(applicant, db.session.get(Project, project_id).members)
            self.assertIn(applicant, db.session.get(Chat, default_chat_id).members)
            self.assertNotIn(applicant, db.session.get(Chat, extra_chat_id).members)
            invitation = db.session.get(Notification, application_id)
            self.assertEqual(invitation.status, 'accepted')
            self.assertTrue(invitation.dismissed)
            self.assertEqual(Notification.query.filter_by(
                user_id=self.outsider_id, project_id=project_id,
                info_type='project_application_accepted',
            ).count(), 1)
        self.login(self.outsider_id)
        self.assertEqual(self.get(f'/chats/{default_chat_id}').status_code, 200)

    def test_duplicate_application_and_acceptance_do_not_duplicate_membership(self):
        project_id = self.create_project()
        application_id = self.apply_to_project(project_id)
        self.assertEqual(self.apply_to_project(project_id), application_id)
        self.login(self.owner_id)
        self.assertEqual(self.post(f'/notifications/{application_id}/accept').status_code, 200)
        self.assertEqual(self.post(f'/notifications/{application_id}/accept').status_code, 400)
        with self.app.app_context():
            chat = Chat.query.filter_by(project_id=project_id).one()
            for table, column, entity_id in [
                (project_members, project_members.c.project_id, project_id),
                (chat_members, chat_members.c.chat_id, chat.id),
            ]:
                rows = db.session.execute(db.select(table).where(
                    column == entity_id, table.c.user_id == self.outsider_id,
                )).all()
                self.assertEqual(len(rows), 1)
            self.assertEqual(Notification.query.filter_by(
                user_id=self.outsider_id, info_type='project_application_accepted',
            ).count(), 1)

    def test_applicant_cannot_accept_reject_or_dismiss_owners_notification(self):
        project_id = self.create_project()
        application_id = self.apply_to_project(project_id)
        for action in ['accept', 'reject', 'dismiss']:
            with self.subTest(action=action):
                self.assertEqual(self.post(f'/notifications/{application_id}/{action}').status_code, 403)
        with self.app.app_context():
            invitation = db.session.get(Notification, application_id)
            self.assertEqual(invitation.status, 'not_answered')
            self.assertFalse(invitation.dismissed)
            self.assertNotIn(db.session.get(User, self.outsider_id), db.session.get(Project, project_id).members)

    def test_rejected_application_does_not_grant_access(self):
        project_id = self.create_project()
        application_id = self.apply_to_project(project_id)
        self.login(self.owner_id)
        response = self.post(f'/notifications/{application_id}/reject')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        self.assertEqual(self.post(f'/notifications/{application_id}/accept').status_code, 400)
        with self.app.app_context():
            applicant = db.session.get(User, self.outsider_id)
            project = db.session.get(Project, project_id)
            self.assertNotIn(applicant, project.members)
            self.assertNotIn(applicant, project.chats.one().members)
            self.assertEqual(db.session.get(Notification, application_id).status, 'rejected')

    def test_chat_invitation_cannot_be_accepted_twice(self):
        self.add_member(self.outsider_id, chat=False)
        self.login(self.owner_id)
        self.assertEqual(self.post(f'/chats/{self.chat_id}/invite/{self.outsider_id}').status_code, 302)
        with self.app.app_context():
            invitation_id = Notification.query.filter_by(invite_type='chat').one().id
        self.login(self.outsider_id)
        first = self.post(f'/notifications/{invitation_id}/accept')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json['redirect'], f'/chats/{self.chat_id}')
        self.assertEqual(self.post(f'/notifications/{invitation_id}/accept').status_code, 400)
        with self.app.app_context():
            rows = db.session.execute(db.select(chat_members).where(
                chat_members.c.chat_id == self.chat_id,
                chat_members.c.user_id == self.outsider_id,
            )).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(Notification.query.filter_by(info_type='chat_invite_accepted_by_user').count(), 1)

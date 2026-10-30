"""Security regressions; run with python -m unittest discover -s tests -v."""

import unittest
from io import BytesIO
from html.parser import HTMLParser
from unittest.mock import patch

from flask import Flask
from flask_socketio import emit
from app import db, socketio
from app.models import Chat, Message, Notification, Project, ProjectMaterial, User
from app.uploads import init_uploads
from tests.support import AppTestCase


class SecurityTests(AppTestCase):
    mutation_routes = [
        '/logout', '/projects/999/apply', '/projects/999/leave',
        '/projects/999/delete', '/projects/999/manage_member/999/remove_member',
        '/chats/999/invite/999', '/chats/999/leave', '/chats/999/kick/999',
        '/chats/999/delete', '/notifications/999/dismiss',
        '/notifications/999/accept', '/notifications/999/reject',
        '/projects/materials/999/delete',
    ]

    def test_mutations_do_not_accept_get(self):
        self.login(self.owner_id)
        for route in self.mutation_routes:
            with self.subTest(route=route):
                self.assertEqual(self.get(route).status_code, 405)
                self.assertEqual(self.client.head(route).status_code, 405)

    def test_mutations_require_csrf(self):
        self.login(self.owner_id)
        for route in self.mutation_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.post(route).status_code, 400)
                self.assertEqual(self.client.post(route, data={'csrf_token': 'invalid'}).status_code, 400)

    def test_get_does_not_delete_records_or_log_out(self):
        self.login(self.owner_id)
        for route in [f'/projects/{self.project_id}/delete', f'/chats/{self.chat_id}/delete', '/logout']:
            self.assertEqual(self.get(route).status_code, 405)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Project, self.project_id))
            self.assertIsNotNone(db.session.get(Chat, self.chat_id))
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], str(self.owner_id))

    def test_legacy_static_uploads_are_not_public(self):
        (self.legacy / 'attachment.txt').write_text('private attachment')
        for path in ['/static/uploads/attachment.txt', '/static/./uploads/attachment.txt',
                     '/static/uploads//attachment.txt', '/static/%75ploads/attachment.txt']:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 404)

    def test_attachment_requires_current_chat_membership(self):
        (self.uploads / 'attachment.txt').write_text('private attachment')
        route = f'/chats/messages/{self.message_id}/attachment'
        self.assertEqual(self.get(route).status_code, 302)
        self.login(self.outsider_id)
        self.assertEqual(self.get(route).status_code, 403)
        self.login(self.owner_id)
        response = self.get(route)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'private attachment')
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', response.headers['Content-Security-Policy'])

    def test_private_materials_and_project_images(self):
        (self.uploads / 'material.txt').write_text('private research')
        (self.uploads / 'project.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        with self.app.app_context():
            db.session.get(Project, self.project_id).image = 'project.svg'
            db.session.commit()
        routes = [f'/projects/materials/{self.material_id}/download', f'/projects/{self.project_id}/image']
        for route in routes:
            with self.subTest(route=route):
                self.client = self.app.test_client()
                self.assertEqual(self.get(route).status_code, 302)
                self.login(self.outsider_id)
                self.assertEqual(self.get(route).status_code, 403)
                self.login(self.owner_id)
                self.assertEqual(self.get(route).status_code, 200)
        self.login(self.outsider_id)
        with self.app.app_context():
            db.session.get(Project, self.project_id).is_public = True
            db.session.commit()
        for route in routes:
            self.assertEqual(self.get(route).status_code, 200)
        # Public project visibility never makes its chat attachments public.
        self.assertEqual(self.get(f'/chats/messages/{self.message_id}/attachment').status_code, 403)

    def test_membership_removal_revokes_downloads(self):
        (self.uploads / 'attachment.txt').write_text('private attachment')
        (self.uploads / 'material.txt').write_text('private research')
        with self.app.app_context():
            outsider = db.session.get(User, self.outsider_id)
            project = db.session.get(Project, self.project_id)
            chat = db.session.get(Chat, self.chat_id)
            project.members.append(outsider)
            chat.members.append(outsider)
            db.session.commit()
        routes = [f'/chats/messages/{self.message_id}/attachment', f'/projects/materials/{self.material_id}/download']
        self.login(self.outsider_id)
        for route in routes:
            self.assertEqual(self.get(route).status_code, 200)
        self.login(self.owner_id)
        response = self.post(f'/projects/{self.project_id}/manage_member/{self.outsider_id}/remove_member')
        self.assertEqual(response.status_code, 302)
        self.login(self.outsider_id)
        for route in routes:
            self.assertEqual(self.get(route, headers={'If-None-Match': '*'}).status_code, 403)

    def test_uploaded_html_is_a_download_and_svg_is_sandboxed(self):
        (self.uploads / 'page.html').write_text('<script>alert(document.cookie)</script>')
        (self.uploads / 'image.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        with self.app.app_context():
            db.session.get(Message, self.message_id).file = 'page.html'
            db.session.get(Project, self.project_id).image = 'image.svg'
            db.session.commit()
        self.login(self.owner_id)
        route = f'/chats/messages/{self.message_id}/attachment'
        download = self.get(route)
        self.assertEqual(download.mimetype, 'application/octet-stream')
        self.assertIn('attachment;', download.headers['Content-Disposition'])
        self.assertEqual(self.get(route + '?preview=1').status_code, 404)
        image = self.get(f'/projects/{self.project_id}/image')
        self.assertEqual(image.mimetype, 'image/svg+xml')
        self.assertIn("sandbox; default-src 'none'", image.headers['Content-Security-Policy'])

    def test_avatar_and_attachment_image_urls(self):
        with self.app.app_context():
            db.session.get(User, self.owner_id).avatar = 'avatar.png'
            db.session.get(Message, self.message_id).file = 'attachment.png'
            db.session.commit()
        for name in ['avatar.png', 'attachment.png']:
            (self.uploads / name).write_bytes(b'image data')
        self.login(self.owner_id)
        for route in [f'/users/{self.owner_id}/avatar', f'/chats/messages/{self.message_id}/attachment?preview=1']:
            response = self.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'image/png')
            self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.get('/static/uploads/avatar.png').status_code, 404)

    def test_migration_moves_legacy_files_and_preserves_defaults(self):
        (self.legacy / 'material.txt').write_text('legacy research')
        (self.legacy / 'default-avatar.svg').write_text('<svg/>')
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['migrate-uploads'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse((self.legacy / 'material.txt').exists())
        self.assertEqual((self.uploads / 'material.txt').read_text(), 'legacy research')
        self.assertTrue((self.legacy / 'default-avatar.svg').exists())
        self.assertIn('Moved 0 uploads', runner.invoke(args=['migrate-uploads']).output)
        self.login(self.owner_id)
        self.assertEqual(self.get(f'/projects/materials/{self.material_id}/download').data, b'legacy research')

    def test_migration_preflights_collisions(self):
        (self.legacy / 'a.txt').write_text('a')
        (self.legacy / 'z.txt').write_text('old')
        (self.uploads / 'z.txt').write_text('new')
        result = self.app.test_cli_runner().invoke(args=['migrate-uploads'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertTrue((self.legacy / 'a.txt').exists())
        self.assertEqual((self.uploads / 'z.txt').read_text(), 'new')

    def test_upload_directory_cannot_be_static(self):
        app = Flask('unsafe-config', static_folder=self.app.static_folder)
        app.config['UPLOAD_FOLDER'] = str(self.legacy)
        with self.assertRaises(ValueError):
            init_uploads(app)

    def test_socket_uploads_are_private_and_rendered_urls_are_authorized(self):
        self.login(self.owner_id)
        client = socketio.test_client(self.app, flask_test_client=self.client)
        self.addCleanup(client.disconnect)
        client.emit('join_chat', {'chat_id': self.chat_id})
        payload = '<img src=x onerror=alert(1)>'
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('send_message', {'chat_id': self.chat_id, 'text': payload,
                                         'file_name': 'research.html', 'file_data': b'<script>alert(1)</script>'})
        self.assertEqual(sent.call_args.args[0], 'new_message')
        self.assertEqual(sent.call_args.kwargs['room'], f'chat_{self.chat_id}')
        message = sent.call_args.args[1]
        self.assertEqual(message['text'], payload)
        self.assertTrue((self.uploads / message['file']).exists())
        self.assertFalse((self.legacy / message['file']).exists())
        self.assertEqual(message['avatar_url'], f'/users/{self.owner_id}/avatar')
        self.assertEqual(self.get(message['attachment_url']).status_code, 200)
        self.assertEqual(self.get('/static/uploads/' + message['file']).status_code, 404)
        self.login(self.outsider_id)
        self.assertEqual(self.get(message['attachment_url']).status_code, 403)

    def test_nonmember_socket_upload_does_not_write_files(self):
        self.login(self.outsider_id)
        client = socketio.test_client(self.app, flask_test_client=self.client)
        self.addCleanup(client.disconnect)
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('send_message', {'chat_id': self.chat_id, 'text': 'intrusion',
                                         'file_name': 'research.txt', 'file_data': b'secret'})
        self.assertEqual(sent.call_args.args[0], 'error')
        self.assertEqual(list(self.uploads.iterdir()), [])

    def test_invalid_socket_attachments_do_not_write_files(self):
        self.login(self.owner_id)
        self.app.config['MAX_CONTENT_LENGTH'] = 4
        client = socketio.test_client(self.app, flask_test_client=self.client)
        self.addCleanup(client.disconnect)
        for fields in [
            {'file_name': 'large.txt', 'file_data': b'12345'},
            {'file_name': 'bad.txt', 'file_data': {'not': 'bytes'}},
            {'file_data': b'1234'},
        ]:
            with self.subTest(fields=fields), patch('app.sockets.emit', wraps=emit) as sent:
                client.emit('send_message', {'chat_id': self.chat_id, 'text': 'test', **fields})
                self.assertEqual(sent.call_args.args[0], 'error')
        self.assertEqual(list(self.uploads.iterdir()), [])
        with self.app.app_context():
            self.assertEqual(Message.query.count(), 1)

    def test_cross_origin_socket_requests_are_rejected(self):
        response = self.get('/socket.io/?EIO=4&transport=polling',
                            headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(response.status_code, 400)

    def test_post_delete_actions(self):
        self.login(self.owner_id)
        (self.uploads / 'material.txt').write_text('research')
        for route in [f'/projects/materials/{self.material_id}/delete',
                      f'/chats/{self.chat_id}/delete', f'/projects/{self.project_id}/delete']:
            with self.subTest(route=route):
                self.assertEqual(self.post(route).status_code, 302)
        self.assertFalse((self.uploads / 'material.txt').exists())
        with self.app.app_context():
            self.assertIsNone(db.session.get(ProjectMaterial, self.material_id))
            self.assertIsNone(db.session.get(Chat, self.chat_id))
            self.assertIsNone(db.session.get(Project, self.project_id))

    def test_project_form_writes_materials_to_private_storage(self):
        self.login(self.owner_id)
        response = self.post('/projects/create', {
            'title': 'New project', 'description': 'Description', 'goals': 'Goals',
            'project_type': 'Project', 'materials': (BytesIO(b'new research'), 'research.txt'),
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            material = ProjectMaterial.query.filter(ProjectMaterial.id != self.material_id).one()
            self.assertEqual((self.uploads / material.filename).read_bytes(), b'new research')
            self.assertFalse((self.legacy / material.filename).exists())

    def test_post_application_and_notifications(self):
        with self.app.app_context():
            db.session.get(Project, self.project_id).is_public = True
            db.session.commit()
        self.login(self.outsider_id)
        self.assertEqual(self.post(f'/projects/{self.project_id}/apply').status_code, 302)
        with self.app.app_context():
            application_id = Notification.query.filter_by(invite_type='project_application').one().id
        self.login(self.owner_id)
        response = self.post(f'/notifications/{application_id}/accept')
        self.assertTrue(response.json['success'])
        self.assertEqual(self.post(f'/notifications/{application_id}/accept').status_code, 400)
        self.assertTrue(self.post(f'/notifications/{application_id}/dismiss').json['success'])
        with self.app.app_context():
            self.assertIn(db.session.get(User, self.outsider_id), db.session.get(Project, self.project_id).members)

    def test_post_chat_invitation_accept_and_reject(self):
        with self.app.app_context():
            project = db.session.get(Project, self.project_id)
            project.members.append(db.session.get(User, self.outsider_id))
            db.session.commit()
        for action in ['reject', 'accept']:
            self.login(self.owner_id)
            self.assertEqual(self.post(f'/chats/{self.chat_id}/invite/{self.outsider_id}').status_code, 302)
            with self.app.app_context():
                invitation_id = Notification.query.filter_by(invite_type='chat', status='not_answered').one().id
            self.login(self.outsider_id)
            result = self.post(f'/notifications/{invitation_id}/{action}')
            self.assertEqual(result.status_code, 200, result.json)
            self.assertTrue(result.json['success'])
        self.assertEqual(result.json['redirect'], f'/chats/{self.chat_id}')

    def test_post_logout_and_single_member_chat_leave(self):
        self.login(self.owner_id)
        self.assertEqual(self.post(f'/chats/{self.chat_id}/leave').status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Chat, self.chat_id))
        self.assertEqual(self.post('/logout').status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)

    def test_templates_use_post_forms_and_keep_confirmation_text_out_of_code(self):
        payload = '\");window.xssExecuted=true;//<img src=x onerror=alert(1)>'
        with self.app.app_context():
            outsider = db.session.get(User, self.outsider_id)
            outsider.username = payload
            project = db.session.get(Project, self.project_id)
            chat = db.session.get(Chat, self.chat_id)
            project.members.append(outsider)
            chat.members.append(outsider)
            db.session.get(Message, self.message_id).text = payload
            db.session.commit()
        self.login(self.owner_id)

        class Elements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.elements = []

            def handle_starttag(self, tag, attrs):
                self.elements.append((tag, dict(attrs)))

        for route in [f'/projects/{self.project_id}', f'/chats/{self.chat_id}',
                      '/projects/feed', '/users/profile', f'/users/view/{self.outsider_id}']:
            with self.subTest(route=route):
                response = self.get(route)
                self.assertEqual(response.status_code, 200)
                parsed = Elements()
                parsed.feed(response.get_data(as_text=True))
                actions = [attrs for tag, attrs in parsed.elements if tag == 'form' and attrs.get('class') == 'action-form']
                self.assertTrue(actions)
                self.assertTrue(all(attrs['method'] == 'post' for attrs in actions))
                self.assertFalse(any(payload in value for _, attrs in parsed.elements
                                     for key, value in attrs.items() if key.startswith('on') and value))
                self.assertFalse(any('onerror' in attrs for _, attrs in parsed.elements))


if __name__ == '__main__':
    unittest.main()

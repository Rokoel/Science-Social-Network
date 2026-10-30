"""Socket.IO authentication, room access, persistence, and membership revocation."""

from unittest.mock import patch

from flask_socketio import emit

from app import db, socketio
from app.models import Message
from tests.support import AppTestCase


class SocketAccessTests(AppTestCase):
    def connect(self, user_id=None):
        http_client = self.app.test_client()
        if user_id is not None:
            with http_client.session_transaction() as session:
                session['_user_id'] = str(user_id)
                session['_fresh'] = True
        client = socketio.test_client(self.app, flask_test_client=http_client)
        self.addCleanup(client.disconnect)
        return client

    def room_contains(self, client, room):
        # Inspect the real room manager, not a mocked join_room call.
        return any(eio_sid == client.eio_sid for _, eio_sid in
                   socketio.server.manager.get_participants('/', room))

    def assert_no_new_messages(self):
        with self.app.app_context():
            self.assertEqual(Message.query.count(), 1)

    def test_anonymous_client_cannot_join_private_rooms_or_send_messages(self):
        client = self.connect()
        client.emit('join_chat', {'chat_id': self.chat_id})
        self.assertFalse(self.room_contains(client, f'chat_{self.chat_id}'))
        self.assertFalse(self.room_contains(client, f'user_{self.owner_id}'))
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('send_message', {'chat_id': self.chat_id, 'text': 'unauthorized'})
        sent.assert_called_once_with('error', {'message': 'Authentication required'})
        self.assert_no_new_messages()

    def test_nonmember_cannot_join_or_send_to_chat(self):
        client = self.connect(self.outsider_id)
        self.assertTrue(self.room_contains(client, f'user_{self.outsider_id}'))
        self.assertFalse(self.room_contains(client, f'user_{self.owner_id}'))
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('join_chat', {'chat_id': self.chat_id})
        self.assertEqual(sent.call_args.args[0], 'error')
        self.assertFalse(self.room_contains(client, f'chat_{self.chat_id}'))
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('send_message', {'chat_id': self.chat_id, 'text': 'unauthorized'})
        self.assertEqual(sent.call_args.args[0], 'error')
        self.assert_no_new_messages()

    def test_member_joins_sends_as_themselves_and_leaves_room(self):
        client = self.connect(self.owner_id)
        client.emit('join_chat', {'chat_id': self.chat_id})
        self.assertTrue(self.room_contains(client, f'chat_{self.chat_id}'))
        # Spying with wraps still executes emission. This avoids depending on the
        # old Flask-SocketIO test client's packet capture with newer python-socketio.
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('send_message', {
                'chat_id': self.chat_id, 'text': 'Research update', 'user_id': self.outsider_id,
            })
        with self.app.app_context():
            message = Message.query.filter_by(text='Research update').one()
            self.assertEqual(message.user_id, self.owner_id)
            self.assertEqual(message.chat_id, self.chat_id)
            message_id = message.id
        self.assertEqual(sent.call_args.args[0], 'new_message')
        self.assertEqual(sent.call_args.args[1]['id'], message_id)
        self.assertEqual(sent.call_args.kwargs, {'room': f'chat_{self.chat_id}'})
        client.emit('leave_chat', {'chat_id': self.chat_id})
        self.assertFalse(self.room_contains(client, f'chat_{self.chat_id}'))

    def test_removed_member_cannot_send_on_existing_connection_or_rejoin(self):
        self.add_member(self.outsider_id)
        client = self.connect(self.outsider_id)
        client.emit('join_chat', {'chat_id': self.chat_id})
        self.login(self.owner_id)
        self.assertEqual(self.post(f'/projects/{self.project_id}/manage_member/{self.outsider_id}/remove_member').status_code, 302)
        with patch('app.sockets.emit', wraps=emit) as sent:
            client.emit('send_message', {'chat_id': self.chat_id, 'text': 'after removal'})
        self.assertEqual(sent.call_args.args[0], 'error')
        self.assert_no_new_messages()
        newcomer = self.connect(self.outsider_id)
        newcomer.emit('join_chat', {'chat_id': self.chat_id})
        self.assertFalse(self.room_contains(newcomer, f'chat_{self.chat_id}'))

    def test_empty_message_and_unknown_chat_do_not_persist(self):
        client = self.connect(self.owner_id)
        for data in [{'chat_id': self.chat_id, 'text': '  '},
                     {'chat_id': 999999, 'text': 'unknown chat'},
                     {'text': 'missing chat'}]:
            with self.subTest(data=data), patch('app.sockets.emit', wraps=emit) as sent:
                client.emit('send_message', data)
                self.assertEqual(sent.call_args.args[0], 'error')
                self.assert_no_new_messages()

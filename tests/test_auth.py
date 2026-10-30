"""Registration and password login through real forms with CSRF enabled."""

from app import db
from app.models import User
from tests.support import AppTestCase


class AuthenticationTests(AppTestCase):
    registration = {
        'username': 'researcher', 'email': 'researcher@example.com',
        'name': 'Ada', 'surname': 'Lovelace',
        'password': 'correct-test-password', 'password2': 'correct-test-password',
    }

    def test_register_login_and_logout(self):
        response = self.post('/register', self.registration)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/login')
        with self.app.app_context():
            user = User.query.filter_by(email=self.registration['email']).one()
            user_id = user.id
            self.assertEqual(user.username, 'researcher')
            self.assertNotEqual(user.password_hash, self.registration['password'])
            self.assertTrue(user.check_password(self.registration['password']))
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)

        response = self.post('/login', {
            'email': self.registration['email'], 'password': self.registration['password'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/projects/feed')
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], str(user_id))
        self.assertEqual(self.get('/users/profile').status_code, 200)
        self.assertEqual(self.post('/logout').status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)
        self.assertIn('/login?next=', self.get('/users/profile').location)

    def test_registration_rejects_invalid_and_duplicate_fields(self):
        cases = [
            ({'username': 'owner'}, 'Please use a different username.'),
            ({'email': 'owner@example.com'}, 'Please use a different email address.'),
            ({'email': 'not-an-email'}, 'Invalid email address.'),
            ({'username': 'ab'}, 'Field must be between 3 and 64 characters long.'),
            ({'password': 'short', 'password2': 'short'}, 'Field must be at least 8 characters long.'),
            ({'password2': 'different-password'}, 'Field must be equal to password.'),
            ({'name': ''}, 'This field is required.'),
        ]
        for fields, error in cases:
            with self.subTest(fields=fields):
                response = self.post('/register', {**self.registration, **fields})
                self.assertEqual(response.status_code, 200)
                self.assertIn(error, response.get_data(as_text=True))
                with self.app.app_context():
                    self.assertEqual(User.query.count(), 2)
                with self.client.session_transaction() as session:
                    self.assertNotIn('_user_id', session)

    def test_login_rejects_wrong_password_and_unknown_account(self):
        with self.app.app_context():
            db.session.get(User, self.owner_id).set_password('owner-password')
            db.session.commit()
        for email in ['owner@example.com', 'unknown@example.com']:
            with self.subTest(email=email):
                response = self.post('/login', {'email': email, 'password': 'incorrect'})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/login')
                self.assertIn('Invalid email or password', self.get('/login').get_data(as_text=True))
                with self.client.session_transaction() as session:
                    self.assertNotIn('_user_id', session)

    def test_authentication_forms_require_csrf(self):
        for route in ['/register', '/login']:
            with self.subTest(route=route):
                self.assertEqual(self.client.post(route, data=self.registration).status_code, 400)
        with self.app.app_context():
            self.assertEqual(User.query.count(), 2)

    def test_anonymous_users_cannot_access_protected_pages(self):
        for route in ['/projects/feed', '/projects/create', '/users/profile',
                      f'/projects/{self.project_id}', f'/chats/{self.chat_id}']:
            with self.subTest(route=route):
                response = self.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login?next=', response.location)

    def test_login_preserves_a_local_next_page(self):
        with self.app.app_context():
            db.session.get(User, self.owner_id).set_password('owner-password')
            db.session.commit()
        response = self.post('/login?next=/users/profile', {
            'email': 'owner@example.com', 'password': 'owner-password',
        })
        self.assertEqual(response.location, '/users/profile')

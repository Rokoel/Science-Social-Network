"""Exercise explicit schema lifecycle on disposable databases."""

import tempfile
import unittest
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, stamp, upgrade
from sqlalchemy import inspect, text

from app import create_app, db
from app.models import User
from config import Config


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)

        class TestConfig(Config):
            TESTING = True
            RATELIMIT_ENABLED = False
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{root / "migration.db"}'
            UPLOAD_FOLDER = str(root / 'uploads')

        self.app = create_app(TestConfig, use_redis=False)
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)

    def assert_schema_matches_models(self):
        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={'compare_type': True})
            self.assertEqual(compare_metadata(context, db.metadata), [])

    def test_factory_does_not_create_tables(self):
        self.assertEqual(inspect(db.engine).get_table_names(), [])

    def test_fresh_upgrade_matches_models_and_can_be_repeated(self):
        upgrade()
        self.assert_schema_matches_models()
        db.session.add(User(username='persisted', email='persisted@example.com'))
        db.session.commit()
        upgrade()
        self.assertEqual(User.query.one().username, 'persisted')
        self.assertEqual(db.session.execute(text('SELECT version_num FROM alembic_version')).scalar(), '0001')

    def test_downgrade_and_upgrade_on_disposable_database(self):
        upgrade()
        downgrade(revision='base')
        self.assertEqual(inspect(db.engine).get_table_names(), ['alembic_version'])
        upgrade()
        self.assert_schema_matches_models()

    def test_matching_legacy_schema_can_be_stamped_without_data_loss(self):
        # Reproduce the old application's create_all schema in this temp DB only.
        db.create_all()
        db.session.add(User(username='legacy', email='legacy@example.com', skills=['Python']))
        db.session.commit()
        self.assert_schema_matches_models()
        stamp(revision='0001')
        upgrade()
        self.assertEqual(User.query.one().username, 'legacy')
        self.assertEqual(User.query.one().skills, ['Python'])
        self.assert_schema_matches_models()

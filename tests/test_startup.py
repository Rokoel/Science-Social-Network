"""Verify the container entrypoint against real, disposable SQLite databases."""

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(shutil.which('sh'), 'Container entrypoint requires a POSIX shell')
class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'startup.db'
        self.marker = self.root / 'command-ran'
        self.env = {
            **os.environ,
            'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', ''),
            'SECRET_KEY': 'entrypoint-test-secret',
            'DATABASE_URL': f'sqlite:///{self.database}',
            'UPLOAD_FOLDER': str(self.root / 'uploads'),
        }

    def run_entrypoint(self):
        return subprocess.run(
            ['sh', 'docker-entrypoint.sh', sys.executable, '-c',
             'import pathlib, sys; pathlib.Path(sys.argv[1]).touch()', str(self.marker)],
            cwd=Path(__file__).resolve().parents[1], env=self.env,
            capture_output=True, text=True, timeout=30,
        )

    def test_upgrade_happens_before_command_and_restart_preserves_data(self):
        result = self.run_entrypoint()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT version_num FROM alembic_version').fetchone(), ('0001',))
            connection.execute("INSERT INTO user (username) VALUES ('retained')")
        self.marker.unlink()
        result = self.run_entrypoint()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT username FROM user').fetchone(), ('retained',))

    def test_failed_migration_prevents_command_starting(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE user (id INTEGER PRIMARY KEY)')
        result = self.run_entrypoint()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertIn('already exists', result.stderr)

    def test_missing_secret_prevents_migrations_and_command(self):
        self.env['SECRET_KEY'] = ''
        result = self.run_entrypoint()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.database.exists())
        self.assertIn('Set SECRET_KEY', result.stderr)

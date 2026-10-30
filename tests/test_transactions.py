"""Project creation must persist every component or none of them."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, func, select
from werkzeug.datastructures import FileStorage

from app import db
from app.models import Chat, Project, ProjectMaterial
from tests.support import AppTestCase


class ProjectTransactionTests(AppTestCase):
    def counts(self):
        with self.app.app_context():
            return {table.name: db.session.scalar(select(func.count()).select_from(table))
                    for table in db.metadata.sorted_tables}

    def submit(self):
        return self.post('/projects/create', {
            'title': 'Atomic project', 'description': 'Test description',
            'goals': 'Test goals', 'project_type': 'Project',
            'image': (BytesIO(b'image bytes'), 'cover.png'),
            'materials': [(BytesIO(b'research data'), 'data.txt'),
                          (BytesIO(b'more data'), 'other.txt')],
        })

    def setUp(self):
        super().setUp()
        self.login(self.owner_id)
        self.existing_file = self.uploads / 'existing.txt'
        self.existing_file.write_bytes(b'keep existing uploads')
        self.before = self.counts()

    def assert_rolled_back(self):
        self.assertEqual(self.counts(), self.before)
        self.assertEqual(list(self.uploads.iterdir()), [self.existing_file])
        self.assertEqual(self.existing_file.read_bytes(), b'keep existing uploads')
        # A subsequent request can still use the session successfully.
        self.create_project(title='Successful retry')

    def test_success_persists_project_uploads_roles_and_default_chat(self):
        response = self.submit()
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            project = Project.query.filter_by(title='Atomic project').one()
            self.assertEqual([u.id for u in project.admins], [self.owner_id])
            self.assertEqual([u.id for u in project.members], [self.owner_id])
            chat = project.chats.one()
            self.assertEqual([u.id for u in chat.members], [self.owner_id])
            self.assertEqual((self.uploads / project.image).read_bytes(), b'image bytes')
            materials = ProjectMaterial.query.filter_by(project_id=project.id).all()
            self.assertEqual(len(materials), 2)
            self.assertEqual({(self.uploads / m.filename).read_bytes() for m in materials},
                             {b'research data', b'more data'})

    def test_chat_insert_failure_rolls_back_every_table_and_upload(self):
        def fail_chat(mapper, connection, target):
            raise RuntimeError('Injected chat insert failure')

        event.listen(Chat, 'before_insert', fail_chat)
        try:
            self.assertEqual(self.submit().status_code, 500)
        finally:
            event.remove(Chat, 'before_insert', fail_chat)
        self.assert_rolled_back()

    def test_final_commit_failure_rolls_back_every_table_and_upload(self):
        with patch.object(db.session, 'commit', side_effect=RuntimeError('Injected commit failure')):
            self.assertEqual(self.submit().status_code, 500)
        self.assert_rolled_back()

    def test_partial_material_write_failure_cleans_all_new_uploads(self):
        original_save = FileStorage.save

        def fail_second_material(storage, destination, *args, **kwargs):
            if storage.filename == 'other.txt':
                Path(destination).write_bytes(b'partial write')
                raise OSError('Injected disk write failure')
            return original_save(storage, destination, *args, **kwargs)

        with patch.object(FileStorage, 'save', fail_second_material):
            self.assertEqual(self.submit().status_code, 500)
        self.assert_rolled_back()

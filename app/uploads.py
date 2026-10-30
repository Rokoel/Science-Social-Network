"""Private upload storage and responses. Callers must authorize the owning record."""

import posixpath
import shutil
from pathlib import Path

import click
from flask import abort, current_app, send_from_directory


DEFAULT_IMAGES = {'default-avatar.svg', 'default-project.svg'}
IMAGE_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
}


def init_uploads(app):
    folder = Path(app.config.get('UPLOAD_FOLDER') or 'uploads')
    if not folder.is_absolute():
        folder = Path(app.instance_path) / folder
    folder = folder.resolve()
    static = Path(app.static_folder).resolve()
    if folder == static or static in folder.parents:
        raise ValueError('UPLOAD_FOLDER must be outside the static directory')
    folder.mkdir(parents=True, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = str(folder)

    # Deny legacy URLs as well, including normalized /static/./uploads/... paths.
    # A reverse proxy must apply the same restriction until legacy files are moved.
    def protected_static(filename):
        normalized = posixpath.normpath(filename.replace('\\', '/'))
        if normalized == 'uploads' or normalized.startswith('uploads/'):
            if normalized not in {f'uploads/{name}' for name in DEFAULT_IMAGES}:
                abort(404)
        return app.send_static_file(filename)

    app.view_functions['static'] = protected_static

    @app.cli.command('migrate-uploads')
    def migrate_uploads():
        """Move legacy static uploads to private storage without changing DB filenames."""
        source = Path(app.static_folder) / 'uploads'
        files = sorted(source.iterdir()) if source.exists() else []
        files = [path for path in files if path.name not in DEFAULT_IMAGES | {'.gitkeep'}]
        # Preflight the entire batch before moving anything; never overwrite files.
        for path in files:
            if path.is_symlink() or not path.is_file():
                raise click.ClickException(f'Expected a regular upload file: {path.name}')
            if (folder / path.name).exists():
                raise click.ClickException(f'Destination already exists: {path.name}')
        for path in files:
            shutil.move(str(path), str(folder / path.name))
        click.echo(f'Moved {len(files)} uploads to {folder}')


def send_upload(filename, *, download_name=None, image=False):
    """Serve an authorized upload without permitting active content or cached access."""
    if not filename or '/' in filename or '\\' in filename or filename in {'.', '..'}:
        abort(404)
    mime = IMAGE_TYPES.get(Path(filename).suffix.lower()) if image else None
    if image and mime is None:
        abort(404)
    response = send_from_directory(
        current_app.config['UPLOAD_FOLDER'], filename,
        as_attachment=not image,
        download_name=download_name or filename,
        mimetype=mime or 'application/octet-stream',
        conditional=False,
    )
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
    return response

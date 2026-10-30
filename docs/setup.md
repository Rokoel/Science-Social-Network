# Setup and maintenance

[Back to the project](../README.md)

Run the commands below from the repository root.

## Docker setup

Requires Docker Engine/Desktop with Docker Compose. From the repository root:

```bash
cp .env.example .env
openssl rand -hex 32
```

Paste the generated value into `SECRET_KEY` in `.env` (on Windows, copy the file
and generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"`).
Then start the application:

```bash
docker compose up --build -d
docker compose ps
docker compose logs app
```

Open http://localhost:5000. Set `APP_PORT` in `.env` if that port is busy.
Compose starts Redis, waits for its health check, and starts the app as a non-root
user. The app entrypoint runs `flask db upgrade` and only starts the Socket.IO
server if migrations succeed. Debug mode is off. Python dependencies, including
transitive dependencies, are pinned in [requirements.lock](../requirements.lock).
Python and Redis images are pinned by digest. Update the lock and image digests
deliberately when upgrading dependencies, then rerun the tests and rebuild.

The `app-data` volume holds both SQLite and private uploads; `redis-data` holds
Redis persistence. `docker compose down` preserves these volumes. **Adding `-v`
deletes them.** Keep the same secret across restarts, and back up the app volume
before upgrades. Existing local `instance` data is not automatically imported.
The app port is bound to localhost and Redis is not published to the host.
This configuration runs one app instance with SQLite; horizontal scaling requires
a shared database and a Socket.IO-aware proxy configuration.

Useful commands:

```bash
docker compose exec app python -m flask --app 'app:create_app(use_redis=False)' db current
docker compose run --rm app python -m unittest discover -s tests -v
docker compose down
```

## Local setup

Use Python 3.11. Create a virtual environment and install the pinned dependencies:

```bash
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows Command Prompt instead:
# venv\Scripts\activate
python -m pip install -r requirements.txt -c requirements.lock
```

For a **new database**, explicitly apply migrations before starting the server:

```bash
python -m flask --app "app:create_app(use_redis=False)" db upgrade
python run.py --no-redis
```

Open http://localhost:5000. To use Redis locally, start Redis and run `python run.py`
without `--no-redis`. Set `REDIS_URL` if it is not at `redis://localhost:6379/0`.
Set `SECRET_KEY` in the environment for a shared deployment. To enable the local
debugger and reloader, add `--debug`; leave this off in deployed environments.
The default SQLite database is `instance/app.db`. `DATABASE_URL` can override it.

## Database migrations

Application startup never creates or updates tables. Migration scripts in
[migrations](../migrations) are the schema history; deploy them with the code.
For an already migrated database, run `db upgrade` on every release (the Docker
entrypoint does this). Repeating it at the current revision leaves data unchanged.

### Existing database from before migrations

Stop the app and back up the database and private uploads first. Revision `0001`
represents the original model schema. If your existing database has all the tables,
columns, indexes, and foreign keys defined in
[that revision](../migrations/versions/0001_initial_application_schema.py), record
that baseline **once**, then apply subsequent upgrades:

```bash
python -m flask --app "app:create_app(use_redis=False)" db stamp 0001
python -m flask --app "app:create_app(use_redis=False)" db upgrade
python -m flask --app "app:create_app(use_redis=False)" db check
```

`stamp` only records a version; it does not create or repair tables. Do not stamp
an empty, partial, or modified schema, or stamp `head` to bypass pending migrations.
Inspect and reconcile schema differences on a backup copy first. A failed upgrade
must be investigated; do not delete your database to resolve a schema error.

### Changing models

On an up-to-date development database:

```bash
python -m flask --app "app:create_app(use_redis=False)" db migrate -m "Describe schema change"
# Review the generated upgrade/downgrade operations before applying them.
python -m flask --app "app:create_app(use_redis=False)" db upgrade
python -m flask --app "app:create_app(use_redis=False)" db check
```

Commit the reviewed migration alongside the model change. SQLite migrations use
Alembic batch mode. The optional `populate_db.py` script requires an empty, migrated
database and refuses to overwrite existing users/projects; it creates demo users
with known passwords, so use it only for local development.

Project creation commits the project, creator roles, materials, and default chat
in one database transaction. Caught failures roll back database changes and remove
newly written uploads, including partial files. Filesystem writes do not participate
in the database transaction: a process crash can still leave orphan files.

## Private uploads

Uploads are stored in `instance/uploads` by default. The application creates this
directory automatically; the application user must have write access. Set
`UPLOAD_FOLDER` to an absolute path to use a different private directory (relative
paths are resolved against `instance`). Paths inside the static directory are rejected.

Serve user uploads only through the application routes. Do not expose
`instance/uploads` (or a custom `UPLOAD_FOLDER`) through a reverse proxy or static
hosting. Remove old public upload copies/CDN caches. If a proxy serves `/static`
directly, deny `/static/uploads/` except the two bundled default images. Flask also
blocks legacy static upload URLs.

Project materials and images require login and, for private projects, membership.
Chat attachments require current chat and project membership. Profile avatars
require login. Downloads disable caching; non-image attachments are served as
downloads, and image responses restrict active content.

## Application and security regression tests

With the virtual environment activated, run:

```bash
python -m unittest discover -s tests -v
```

The tests use isolated temporary SQLite databases and upload directories;
they do not alter application data or require Redis or external services. CSRF
protection stays enabled. The runner uses Python's standard-library `unittest`,
so no additional test dependencies are needed. Fixtures apply the real migrations.

| Suite | Coverage |
| --- | --- |
| [Startup](../tests/test_startup.py) | Entrypoint migration ordering, data preservation on restart, and refusal to start on migration failure or missing secret (POSIX shell required) |
| [Migrations](../tests/test_migrations.py) | No schema writes at startup, fresh/repeated upgrades, schema parity, downgrade/upgrade, and legacy baseline data preservation |
| [Transactions](../tests/test_transactions.py) | Successful project creation and rollback of all rows/uploads after chat, commit, and partial file-write failures |
| [Authentication](../tests/test_auth.py) | Registration, password hashing, validation and duplicates, valid/invalid login, logout, anonymous access, and CSRF |
| [Projects](../tests/test_projects.py) | Creation, private visibility, owner/admin/member permissions, creator protection, role changes, and removal from every project chat |
| [Applications and invitations](../tests/test_notifications.py) | Acceptance into the default chat, rejection, recipient authorization, duplicate applications, and repeated acceptance without duplicate memberships or notifications |
| [Socket.IO](../tests/test_sockets.py) | Anonymous/nonmember denial, actual room membership, authenticated message authorship and persistence, room exit, and denial of sends/rejoins after removal |
| [Security](../tests/test_security.py) | POST-only mutations, CSRF, private downloads, revoked download access, upload migration, unsafe content, and Socket.IO uploads |

The application acceptance regression creates a project through its form, submits
an application, accepts it, and verifies access to the chat created with that project.
It also checks that acceptance does not grant access to unrelated discussion chats.

To run only one suite:

```bash
python -m unittest tests.test_notifications -v
```

Socket tests use Flask-SocketIO's in-process client and inspect its real room
manager and database writes. Outgoing events are observed with spies that still
execute the real emitter; these tests do not replace a browser/network transport test.

For the browser rendering checks, serve the repository locally:

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/tests/rendering.html`. The page reports assertions for
hostile HTML, unsafe URLs, confirmation text, and generated POST forms. Stop the
test server when finished; it is only for local testing.

# CLAUDE.md

## Project Documentation

- `docs/architecture.md` - system design, data pipeline, database schema, key decisions
- `docs/data-model.md` - database tables, columns, types, constraints, relationships
- `docs/api-reference.md` - JSON API endpoints, request/response formats
- `docs/development.md` - setup, seeding, running tests, migrations, CI/CD, deployment, project structure
- `docs/coding_standards.md` - patterns and conventions for coding agents
- `docs/testing-guide.md` - what to test, what not to test, stack-specific guidance
- `docs/visual-testing.md` - Selenium screenshot testing

## Environment Setup

PostgreSQL is installed and available in this environment. Start it with `service postgresql start` if it's not running. The test database is `email_reviewer_test` on localhost:5432 (user: `test`, password: `test`).

The test database user and database already exist. Do not waste time recreating them. If pytest fails with an authentication error, create the user and database:

```
su - postgres -c "psql -c \"CREATE USER test WITH PASSWORD 'test' CREATEDB;\""
su - postgres -c "psql -c \"CREATE DATABASE email_reviewer_test OWNER test;\""
```

Dependencies are installed in the system Python (`/usr/local/bin/python`). Always run tests with `python -m pytest` (not bare `pytest`) to use the correct Python environment. Do not install packages or troubleshoot virtualenvs - the system Python has everything.

## Testing

Read `docs/testing-guide.md` before writing or modifying any test.

Always run tests - do not skip them.

## Documentation

When making a change that affects documented behaviour (new endpoints, model changes, config changes, enum additions, migration additions), update the relevant docs. When adding a new feature, review existing documentation in its entirety rather than just appending a new section. Other parts of the docs may reference the area you changed and need updating to stay accurate.

## Style

No meta commentary in code comments, commit messages, or documentation. State what the code does or why a decision was made. Do not narrate the act of writing it, explain that you made a change, or add filler like "This is a simple function that..." or "Updated to reflect the new...".

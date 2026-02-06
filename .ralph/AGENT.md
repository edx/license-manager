# Ralph Agent Configuration

## Prerequisites

- Set `DEVSTACK_WORKSPACE` environment variable to the folder containing this repo and the devstack repo
- Set up [Open edX devstack](https://github.com/openedx/devstack)

## Build Instructions

Assume the dev containers are already running.

## Test Instructions

You must enter a docker container shell to run tests and linters.
```bash
# Run tests in Docker
make app-shell
# then inside container:
pytest

# Run specific test
make app-shell
# then inside container:
pytest path/to/test_file.py::TestClass::test_method
```

## Run Instructions

```bash
# Start all services (includes Redis from devstack)
make dev.up

# Open bash shell in app container
make app-shell

# Stop containers without removing data
make dev.stop

# Stop and remove containers
make dev.down

# Apply database migrations
make dev.migrate

# Access the server
# Server runs on localhost:18170
# Admin interface at /admin with credentials edx/edx
```

## Quality & Maintenance

You must enter a docker container shell to run tests and linters.
```bash
make app-shell

# Run style checks and linting
make quality

# Sort Python imports
make isort

# Check for PII annotations
make pii_check

# Update requirements
make requirements
```

## Notes
- Server runs on `localhost:18170`
- Admin credentials: `edx/edx`
- Line length: 120 characters
- Uses Django with pytest for testing
- Celery for background tasks

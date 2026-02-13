# Ralph Agent Configuration

## Prerequisites

- Set `DEVSTACK_WORKSPACE` environment variable to the folder containing this repo and the devstack repo
- Set up [Open edX devstack](https://github.com/openedx/devstack)

## Build Instructions

Assume the dev containers are already running.

## Test Instructions

You must enter a docker container shell to run tests and linters.
```bash
# Run tests via docker container
docker compose run app bash -c "pytest -c pytest.local.ini path/to/test_file.py::TestClass::test_method"
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

You must use a docker container shell to run tests and linters.

```bash
# Run tests via docker container
docker compose run app bash -c "make isort style"
docker compose run app bash -c "make lint"
docker compose run app bash -c "make pii_check"
```

## Notes
- Server runs on `localhost:18170`
- Admin credentials: `edx/edx`
- Line length: 120 characters
- Uses Django with pytest for testing
- Celery for background tasks

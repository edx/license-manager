# Ralph Agent Configuration

## Prerequisites

- Set `DEVSTACK_WORKSPACE` environment variable to the folder containing this repo and the devstack repo
- Set up [Open edX devstack](https://github.com/openedx/devstack)

## Build Instructions

Assume the dev containers are already running.

## Test and Quality Instructions

You must use a docker container shell to run tests and linters.
```bash
# Run tests via docker container
docker run --rm edxops/license-manager-dev:latest bash -c "DJANGO_SETTINGS_MODULE=license_manager.settings.test pytest -c pytest.local.in license_manager/apps/subscriptions/tests/test_models.py::TestClass::test_method"
docker run --rm edxops/license-manager-dev:latest bash -c "DJANGO_SETTINGS_MODULE=license_manager.settings.test make quality"
```


## Notes
- Line length: 120 characters
- Uses Django with pytest for testing
- Celery for background tasks

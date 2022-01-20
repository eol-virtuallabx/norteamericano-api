# Norteamericano API
![https://github.com/eol-virtuallabx/norteamericano-api/actions](https://github.com/eol-virtuallabx/norteamericano-api/workflows/Python%20application/badge.svg)

# Install App

    docker-compose exec lms pip install -e /openedx/requirements/norteamericano-api
    docker-compose exec cms pip install -e /openedx/requirements/norteamericano-api

## TESTS
**Prepare tests:**

    > cd .github/
    > docker-compose run cms /openedx/requirements/norteamericano-api/.github/test.sh

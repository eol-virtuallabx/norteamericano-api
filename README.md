# Uchile Edx Login
![https://github.com/eol-uchile/norteamericanoapi/actions](https://github.com/eol-uchile/norteamericanoapi/workflows/Python%20application/badge.svg)

# Install App

    docker-compose exec lms pip install -e /openedx/requirements/norteamericanoapi && docker-compose exec cms pip install -e /openedx/requirements/norteamericanoapi

## TESTS
**Prepare tests:**

    > cd .github/
    > docker-compose run cms /openedx/requirements/norteamericanoapi/.github/test.sh

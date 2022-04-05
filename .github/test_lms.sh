#!/bin/dash
pip install -e git+https://github.com/eol-virtuallabx/norteamericano_custom_form@cd360ec9903b4833d5d4572ff29cda7b36ff6c5b#egg=norteamericano_custom_form
pip install -e /openedx/requirements/norteamericanoapi

cd /openedx/requirements/norteamericanoapi
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/norteamericanoapi

#openedx-assets collect --settings=prod.assets
#EDXAPP_TEST_MONGO_HOST=mongodb python -Wd -m pytest --ds=cms.envs.test --junitxml=/openedx/edx-platform/reports/cms/nosetests.xml /openedx/requirements/norteamericanoapi/norteamericanoapi/tests.py
DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest norteamericanoapi/tests/tests_lms.py
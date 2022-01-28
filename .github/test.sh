#!/bin/dash
pip install -e git+https://github.com/eol-virtuallabx/norteamericano_custom_form@d86b4eb3188387e1bd871aa34fcbb79d6d85df36#egg=norteamericano_custom_form
pip install -e /openedx/requirements/norteamericanoapi

cd /openedx/requirements/norteamericanoapi
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/norteamericanoapi

#openedx-assets collect --settings=prod.assets
EDXAPP_TEST_MONGO_HOST=mongodb python -Wd -m pytest --ds=cms.envs.test --junitxml=/openedx/edx-platform/reports/cms/nosetests.xml /openedx/requirements/norteamericanoapi/norteamericanoapi/tests.py::TestEnrollCSV::test_enroll_csv

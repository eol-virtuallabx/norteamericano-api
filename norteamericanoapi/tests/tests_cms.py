#!/usr/bin/env python
# -*- coding: utf-8 -*-
from mock import patch, Mock, MagicMock
from collections import namedtuple
from django.urls import reverse
from django.test import TestCase, Client
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from urllib.parse import parse_qs
from opaque_keys.edx.locator import CourseLocator
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from openedx.core.djangoapps.models.course_details import CourseDetails
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from common.djangoapps.student.tests.factories import CourseEnrollmentAllowedFactory, UserFactory, CourseEnrollmentFactory
from common.djangoapps.student.auth import has_course_author_access
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from common.djangoapps.course_action_state.models import CourseRerunState
from common.djangoapps.course_action_state.managers import CourseRerunUIStateManager
from norteamericanoapi.rest_api import ReRunPendingCourseApi, ReRunApi, CourseDataApi
from norteamericanoapi.serializers import ReRunPendingCourseSerializer, ReRunSerializer, CourseDataSerializer
from django.test.utils import override_settings
from unittest.case import SkipTest
import re
import json
import urllib.parse
try:
    from norteamericano_form.models import NAExtraInfo
    HAVE_NA_MODEL = True
except ImportError:
    HAVE_NA_MODEL = False

class TestReRunPendingCourse(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunPendingCourse, self).setUp()
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            content_type = ContentType.objects.get_for_model(NAExtraInfo)
            permission = Permission.objects.get(
                codename='na_instructor_staff',
                content_type=content_type,
            )
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.user_staff.user_permissions.add(permission)
            self.client.login(username='testuser3', password='12345')

    def test_pending_course(self):
        """
            test get pending rerun courses
        """
        sourse_course_key = CourseLocator('source-Org', 'source-Course', 'source-Run')
        destination_course_key = CourseLocator('destination-Org', 'destination-Course', 'destination-Run')
        CourseRerunState.objects.initiated(
            sourse_course_key, destination_course_key=destination_course_key, user=self.user_staff, display_name="test course"
        )
        response = self.client.get(reverse('norteamericanoapi:pending-courses'))
        self.assertEqual(response.status_code, 200)
        r = response.json()
        pending_courses = [ {'new_course_id':str(destination_course_key), 'origen_course_id': str(sourse_course_key), 'display_name': "test course", 'state': 'in_progress'} ]
        expect = {'result': 'success', 'courses': pending_courses}
        self.assertEqual(r, expect)
        new_client = Client()
        response = new_client.get(reverse('norteamericanoapi:pending-courses'))
        self.assertEqual(response.status_code, 404)

    def test_pending_course_post(self):
        """
            test get pending rerun courses wrong method
        """
        response = self.client.post(reverse('norteamericanoapi:pending-courses'))
        self.assertEqual(response.status_code, 405)

class TestReRunPendingCourseSerializers(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunPendingCourseSerializers, self).setUp()
        self.created_user = UserFactory()
        self.new_course = CourseLocator("test_org", "test_course_num", "test_run")
        CourseRerunState.objects.initiated(
            source_course_key=CourseLocator("source_org", "source_course_num", "source_run"),
            destination_course_key=self.new_course,
            user=self.created_user,
            display_name="destination course name",
        )

    def test_pending_rerun_serializers(self):
        """
            Test pending rerun serializers
        """
        body = {
            "course":'all'
        }
        serializer = ReRunPendingCourseSerializer(data=body)
        self.assertTrue(serializer.is_valid())

        body = {
            "course":str(self.new_course)
        }
        serializer = ReRunPendingCourseSerializer(data=body)
        self.assertTrue(serializer.is_valid())
    
    def test_pending_rerun_serializers_not_valid(self):
        """
            test pending rerun serializers when is not valid
        """
        body = {
            "course":'course-v1:eol+Test202v2 2022'
        }
        serializer = ReRunPendingCourseSerializer(data=body)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(len(serializer.errors), 1)
        self.assertEqual(str(serializer.errors['course'][0]), "Course key not valid or dont exists: {}".format(body['course']))

        body = {
            "course":'course-v1:eol+Test202v2+2022'
        }
        serializer = ReRunPendingCourseSerializer(data=body)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(len(serializer.errors), 1)
        self.assertEqual(str(serializer.errors['course'][0]), "Course key not valid or dont exists: {}".format(body['course']))

class TestReRunPendingCourseAPI(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunPendingCourseAPI, self).setUp()
        self.created_user = UserFactory()
        self.new_course = CourseLocator("test_org", "test_course_num", "test_run")
        self.source_course = CourseLocator("source_org", "source_course_num", "source_run")
        CourseRerunState.objects.initiated(
            source_course_key=self.source_course,
            destination_course_key=self.new_course,
            user=self.created_user,
            display_name="destination course name",
        )

    def test_pending_rerun_api(self):
        """
            Test pending rerun api
        """
        body = {
            "course":'all'
        }
        base_url ='https://test.web.st/login'
        expected = [{'new_course_id':str(self.new_course), 'origen_course_id': str(self.source_course), 'display_name': 'destination course name', 'state': 'in_progress', 'new_course_url': '{}course/{}'.format(base_url,str(self.new_course))}]
        response = ReRunPendingCourseApi().pending_courses(body, base_url)
        self.assertEqual(response, expected)

        body = {
            "course":str(self.new_course)
        }
        response = ReRunPendingCourseApi().pending_courses(body, base_url)
        self.assertEqual(response, expected)

class TestReRun(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRun, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2022',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        with patch('common.djangoapps.student.models.cc.User.save'):
            content_type = ContentType.objects.get_for_model(NAExtraInfo)
            permission = Permission.objects.get(
                codename='na_instructor_staff',
                content_type=content_type,
            )
            # staff user
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.user_staff.user_permissions.add(permission)
            self.client.login(username='testuser3', password='12345')
            # user student
            self.student_client = Client()
            self.student = UserFactory(
                username='student',
                password='12345',
                email='student@edx.org')
            self.student.user_permissions.add(permission)
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course.id)
            self.assertTrue(
                self.student_client.login(
                    username='student',
                    password='12345'))
    
    def test_rerun_get(self):
        """
            test rerun courses GET method
        """
        response = self.client.get(reverse('norteamericanoapi:rerun'))
        self.assertEqual(response.status_code, 200)

        new_client = Client()
        response = new_client.get(reverse('norteamericanoapi:rerun'))
        self.assertEqual(response.status_code, 404)

    def test_rerun_anonymous_user(self):
        """
            test rerun courses when user is anonymous
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        new_client = Client()
        response = new_client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 404)
    
    def test_rerun_wrong_file(self):
        """
            test rerun courses when csv file is not file
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "archivo": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertTrue("id=\"not_file\"" in response._container[0].decode())
        post_data = {
            "file": 'mock',
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertTrue("id=\"not_file\"" in response._container[0].decode())
    
    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun(self, csv_reader):
        """
            test rerun courses POST method
        """
        # rerun from mongo into split
        split_course3_id = CourseLocator(
            org="edx3", course="split3", run="rerun_test"
        )
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        CourseRerunState.objects.initiated(self.course.id, split_course3_id, self.user, fields['display_name'])

        data_csv = [str(self.course.id), str(split_course3_id), fields['display_name'], '15:00 25/12/2022','15:00 25/12/2023']

        aux = '{};{}\r\n'.format(';'.join(data_csv), 'Procesandose')
        csv_reader.return_value = [data_csv]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(has_course_author_access(self.user, split_course3_id), "Didn't grant access")
        rerun_state = CourseRerunState.objects.find_first(course_key=split_course3_id)
        self.assertEqual(rerun_state.state, CourseRerunUIStateManager.State.SUCCEEDED)
        data = [x.decode() for x in response._container]
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC);Estado\r\n', aux]
        self.assertEqual(data, expect)

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun_wrong_datetime(self, csv_reader):
        """
            test rerun courses when start_date or end_date are wrong
        """
        # rerun from mongo into split
        split_course3_id = CourseLocator(
            org="edx3", course="split3", run="rerun_test"
        )
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        data_csv = [str(self.course.id), str(split_course3_id), fields['display_name'], '15:00 25-12-2022','15:00 25/12/2023']
        aux = '{};{}\r\n'.format(';'.join(data_csv), 'Formato incorrecto en las fechas del curso')
        csv_reader.return_value = [data_csv]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC);Estado\r\n', aux]
        self.assertEqual(data, expect)
    
    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun_wrong_course_id(self, csv_reader):
        """
            test rerun courses when origin course id is wrong
        """
        # rerun from mongo into split
        split_course3_id = CourseLocator(
            org="edx3", course="split3", run="rerun_test"
        )
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        data_csv = ['asdsadsad', str(split_course3_id), fields['display_name'], '15:00 25/12/2022','15:00 25/12/2023']
        aux = '{};{}\r\n'.format(';'.join(data_csv), 'Formato del course_id incorrecto o el curso no existe')
        csv_reader.return_value = [data_csv]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC);Estado\r\n', aux]
        self.assertEqual(data, expect)
    
    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun_wrong_new_course_id(self, csv_reader):
        """
            test rerun courses wwhen new course id is wrong
        """
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        data_csv = [str(self.course.id), 'course-v2:eol+Test202+2022_2', fields['display_name'], '15:00 25/12/2022','15:00 25/12/2023']
        aux = '{};{}\r\n'.format(';'.join(data_csv), 'Formato del nuevo course_id incorrecto')
        csv_reader.return_value = [data_csv]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC);Estado\r\n', aux]
        self.assertEqual(data, expect)
    
    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun_wrong_new_course_id_2(self, csv_reader):
        """
            test rerun courses wwhen new course id is wrong
        """
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        data_csv = [str(self.course.id), str(self.course.id), fields['display_name'], '15:00 25/12/2022','15:00 25/12/2023']
        aux = '{};{}\r\n'.format(';'.join(data_csv), 'El nuevo course id ya existe')
        csv_reader.return_value = [data_csv]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC);Estado\r\n', aux]
        self.assertEqual(data, expect)

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun_no_permission(self, csv_reader):
        """
            test rerun courses when user dont have permission
        """
        # rerun from mongo into split
        split_course3_id = CourseLocator(
            org="edx3", course="split3", run="rerun_test"
        )
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        data_csv = [str(self.course.id), str(split_course3_id), fields['display_name'], '15:00 25/12/2022','15:00 25/12/2023']
        aux = '{};{}\r\n'.format(';'.join(data_csv), 'Usuario no tiene permisos en el curso')
        csv_reader.return_value = [data_csv]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.student_client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC);Estado\r\n', aux]
        self.assertEqual(data, expect)

class TestReRunSerializers(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunSerializers, self).setUp()
        self.new_course = CourseLocator("test_org", "test_course_num", "test_run")
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2022',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)

    def test_rerun_serializers(self):
        """
            Test rerun serializers
        """
        body = {
            "source_course":str(self.course.id),
            "new_course":str(self.new_course),
            "display_name":"test name",
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2023"
        }
        serializer = ReRunSerializer(data=body)
        self.assertTrue(serializer.is_valid())

    def test_rerun_serializers_not_valid(self):
        """
            test rerun serializers when is not valid
        """
        body = {
            "source_course":str(self.new_course),
            "new_course":str(self.course.id),
            "display_name":"",
            "start_date":"00:00-01/01/2022",
            "end_date":"00:00 01/30/2023"
        }
        serializer = ReRunSerializer(data=body)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(len(serializer.errors), 5)
        self.assertEqual(str(serializer.errors['source_course'][0]), "Source Course key not valid or dont exists: {}".format(body["source_course"]))
        self.assertEqual(str(serializer.errors['new_course'][0]), "New Course key already exists: {}".format(body['new_course']))
        self.assertEqual(str(serializer.errors['display_name'][0]), 'This field may not be blank.')
        self.assertEqual(str(serializer.errors['start_date'][0]), "Wrong format start_date: {}, must be 'HH:MM DD/MM/YYYY'".format(body['start_date']))
        self.assertEqual(str(serializer.errors['end_date'][0]), "Wrong format end_date: {}, must be 'HH:MM DD/MM/YYYY'".format(body['end_date']))

        body = {
            "source_course":str(self.course.id),
            "new_course":str(self.new_course),
            "display_name":"test name",
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2021"
        }
        serializer = ReRunSerializer(data=body)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(len(serializer.errors), 1)
        self.assertEqual(str(serializer.errors['non_field_errors'][0]), "end_date must be later than the start_date.")

class TestReRunAPI(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunAPI, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2022',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)

    def test_rerun_api(self):
        """
            Test rerun api
        """
        # rerun from mongo into split
        split_course3_id = CourseLocator(
            org="edx3", course="split3", run="rerun_test"
        )
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        CourseRerunState.objects.initiated(self.course.id, split_course3_id, self.user_staff, fields['display_name'])

        body = {
            "source_course":str(self.course.id),
            "new_course":str(split_course3_id),
            "display_name":"test name",
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2023"
        }
        base_url ='https://test.web.st/login'
        expected = {'new_course_url':'{}course/{}'.format(base_url,str(split_course3_id)), "status": 'Procesandose','result':'success'}

        response = ReRunApi().rerun_courses(body, self.user_staff, base_url)
        self.assertTrue(has_course_author_access(self.user_staff, split_course3_id), "Didn't grant access")
        rerun_state = CourseRerunState.objects.find_first(course_key=split_course3_id)
        self.assertEqual(rerun_state.state, CourseRerunUIStateManager.State.SUCCEEDED)
        self.assertEqual(response, expected)

class TestCourseDataSerializers(ModuleStoreTestCase):
    def setUp(self):
        super(TestCourseDataSerializers, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2022',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)

    def test_coursedata_serializers(self):
        """
            Test coursedata serializers
        """
        body = {
            "course":str(self.course.id),
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2023"
        }
        serializer = CourseDataSerializer(data=body)
        self.assertTrue(serializer.is_valid())

        body = {
            "course":str(self.course.id),
            "end_date":"00:00 01/01/2023"
        }
        serializer = CourseDataSerializer(data=body)
        self.assertTrue(serializer.is_valid())

    def test_coursedata_serializers_not_valid(self):
        """
            test coursedata serializers when is not valid
        """
        body = {
            "course":'course-v1:eol+Test202v2 2022',
            "start_date":"00:00-01/01/2022",
            "end_date":"00:00 01/30/2023"
        }
        serializer = CourseDataSerializer(data=body)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(len(serializer.errors), 3)
        self.assertEqual(str(serializer.errors['course'][0]), "Course key not valid or dont exists: {}".format(body["course"]))
        self.assertEqual(str(serializer.errors['start_date'][0]), "Wrong format start_date: {}, must be 'HH:MM DD/MM/YYYY'".format(body['start_date']))
        self.assertEqual(str(serializer.errors['end_date'][0]), "Wrong format end_date: {}, must be 'HH:MM DD/MM/YYYY'".format(body['end_date']))

        body = {
            "course":str(self.course.id),
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2021"
        }
        serializer = CourseDataSerializer(data=body)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(len(serializer.errors), 1)
        self.assertEqual(str(serializer.errors['non_field_errors'][0]), "end_date must be later than the start_date.")

class TestCourseDataAPI(ModuleStoreTestCase):
    def setUp(self):
        super(TestCourseDataAPI, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2022',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)

    def test_coursedata_api(self):
        """
            Test coursedata api
        """
        jsondetails = CourseDetails.fetch(self.course.id)
        body = {
            "course":str(self.course.id),
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2023"
        }
        response = CourseDataApi().set_data(body, self.user_staff)
        self.assertTrue(response)
        jsondetails = CourseDetails.fetch(self.course.id)
        self.assertEqual(jsondetails.start_date.strftime("%H:%M %d/%m/%Y"), body['start_date'])
        self.assertEqual(jsondetails.end_date.strftime("%H:%M %d/%m/%Y"), body['end_date'])

    def test_coursedata_api_error(self):
        """
            Test coursedata api wrong date
        """
        jsondetails = CourseDetails.fetch(self.course.id)
        body = {
            "course":str(self.course.id),
            "start_date":"00:00 01/01/2022",
            "end_date":"00:00 01/01/2020"
        }
        response = CourseDataApi().set_data(body, self.user_staff)
        self.assertFalse(response)

class TestReRunExportCSV(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunExportCSV, self).setUp()
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            content_type = ContentType.objects.get_for_model(NAExtraInfo)
            permission = Permission.objects.get(
                codename='na_instructor_staff',
                content_type=content_type,
            )
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.user_staff.user_permissions.add(permission)
            self.client.login(username='testuser3', password='12345')

    def test_rerun_export(self):
        """
            test export rerun CSV file
        """
        response = self.client.get(reverse('norteamericanoapi:rerun-export'))
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['',"Course Id;Nuevo Course Id;Nombre curso nuevo;Fecha de Inicio(UTC);Fecha de Termino(UTC)\r\n"]
        self.assertEqual(data, expect)

        new_client = Client()
        response = new_client.get(reverse('norteamericanoapi:rerun-export'))
        self.assertEqual(response.status_code, 404)

    def test_rerun_export_post(self):
        """
            test export rerun CSV file wrong method
        """
        response = self.client.post(reverse('norteamericanoapi:rerun-export'))
        self.assertEqual(response.status_code, 405)
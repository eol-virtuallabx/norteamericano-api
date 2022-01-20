#!/usr/bin/env python
# -*- coding: utf-8 -*-
from mock import patch, Mock, MagicMock
from collections import namedtuple
from django.urls import reverse
from django.test import TestCase, Client
from django.test import Client
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from urllib.parse import parse_qs
from opaque_keys.edx.locator import CourseLocator
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from common.djangoapps.student.tests.factories import CourseEnrollmentAllowedFactory, UserFactory, CourseEnrollmentFactory
from common.djangoapps.student.auth import has_course_author_access
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from common.djangoapps.course_action_state.models import CourseRerunState
from common.djangoapps.course_action_state.managers import CourseRerunUIStateManager
from .utils import create_user_by_data, generate_username
from django.test.utils import override_settings
import re
import json
import urllib.parse

class TestEnrollCSV(ModuleStoreTestCase):
    def setUp(self):
        super(TestEnrollCSV, self).setUp()
        self.course = CourseFactory.create(
            org='mss',
            course='999',
            display_name='2022',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course.id)
        self.course2 = CourseFactory.create(
            org='mss',
            course='222',
            display_name='2021',
            emit_signals=True)
        aux = CourseOverview.get_from_id(self.course2.id)
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.client.login(username='testuser3', password='12345')

            # user instructor
            self.client_instructor = Client()
            user_instructor = UserFactory(
                username='instructor',
                password='12345',
                email='instructor@edx.org')
            role = CourseInstructorRole(self.course.id)
            role2 = CourseInstructorRole(self.course2.id)
            role.add_users(user_instructor)
            role2.add_users(user_instructor)
            self.client_instructor.login(
                username='instructor', password='12345')

            # user staff course
            self.staff_user_client = Client()
            self.staff_user = UserFactory(
                username='staff_user',
                password='12345',
                email='staff_user@edx.org')
            CourseEnrollmentFactory(
                user=self.staff_user,
                course_id=self.course.id)
            CourseStaffRole(self.course.id).add_users(self.staff_user)
            self.assertTrue(
                self.staff_user_client.login(
                    username='staff_user',
                    password='12345'))

            # user student
            self.student_client = Client()
            self.student = UserFactory(
                username='student',
                password='12345',
                email='student@edx.org')
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course.id)
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course2.id)
            self.assertTrue(
                self.student_client.login(
                    username='student',
                    password='12345'))

    @override_settings(REGISTRATION_EMAIL_PATTERNS_DISALLOWED=True)
    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_enroll_csv(self, csv_reader):
        """
            Test enroll user csv
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        csv_reader.return_value = [
            [self.student.email, 'a', 'b'],
            ['aux.student2@edx.org', 'User', 'LastName'],
            ['@edx.org', 'User', 'LastName'],
            ['@edx.org', 'User', 'LastName1', 'LastName2', 'LastName3', 'LastName4'],
            ['@edx.org'],
            ]
        post_data = {
            "file": Mock(file=mock_file_object),
            'course': str(self.course.id),
            'mode': 'honor',
        }
        response = self.client.post(reverse('norteamericanoapi:enroll'), post_data)
        self.assertTrue(User.objects.filter(email="aux.student2@edx.org").exists())
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        data_student = '{};{};{};{};{}\r\n'.format('aux.student2@edx.org', 'User','LastName','user_lastname', 'Creado e Inscrito')
        data_student_2 = '{};{};{};{};{}\r\n'.format(self.student.email, 'a','b',self.student.username, 'Inscrito')
        data_student_3 = '{};{};{};{};{}\r\n'.format('@edx.org', 'User','LastName','', 'Error, Revise los datos si estan correctos')
        data_student_4 = '{};{};{};{};{}\r\n'.format('@edx.org', 'User','LastName1','LastName2', 'Error, Revise los datos si estan correctos')
        data_student_5 = '{};{};{};{};{}\r\n'.format('@edx.org', '','','', 'Error, Revise los datos si estan correctos')
        expect = ['',"Email;Nombres;Apellidos;Username;Estado\r\n", data_student_2, data_student, data_student_3, data_student_4, data_student_5]
        self.assertEqual(data, expect)

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_enroll_csv_anonymous_user(self, csv_reader):
        """
            Test enroll user csv view when user is anonymous
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        csv_reader.return_value = [
            ['aux.student2@edx.org', 'User', 'LastName']
            ]
        post_data = {
            "file": Mock(file=mock_file_object),
            'course': str(self.course.id),
            'mode': 'honor',
        }
        new_client = Client()
        response = new_client.post(reverse('norteamericanoapi:enroll'), post_data)
        self.assertEqual(response.status_code, 404)

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_enroll_csv_student_user(self, csv_reader):
        """
            Test enroll user csv view when user is student
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        csv_reader.return_value = [
            ['aux.student2@edx.org', 'User', 'LastName']
            ]
        post_data = {
            "file": Mock(file=mock_file_object),
            'course': str(self.course.id),
            'mode': 'honor',
        }
        response = self.student_client.post(reverse('norteamericanoapi:enroll'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"error_permission\"" in response._container[0].decode())

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_enroll_csv_no_course(self, csv_reader):
        """
            Test enroll user csv view when course params dont exists
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        csv_reader.return_value = [
            ['aux.student2@edx.org', 'User', 'LastName']
            ]
        post_data = {
            "file": Mock(file=mock_file_object),
            'mode': 'honor',
        }
        response = self.client.post(reverse('norteamericanoapi:enroll'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"not_course\"" in response._container[0].decode())

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_enroll_csv_wrong_course(self, csv_reader):
        """
            Test enroll user csv view when course id is wrong
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        csv_reader.return_value = [
            ['aux.student2@edx.org', 'User', 'LastName']
            ]
        post_data = {
            "file": Mock(file=mock_file_object),
            'course': 'course-v1:eol+Test101+2021',
            'mode': 'honor',
        }
        response = self.client.post(reverse('norteamericanoapi:enroll'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"wrong_course\"" in response._container[0].decode())

    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_enroll_csv_wrong_mode(self, csv_reader):
        """
            Test enroll user csv view when enroll mode is wrong
        """
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        csv_reader.return_value = [
            ['aux.student2@edx.org', 'User', 'LastName']
            ]
        post_data = {
            "file": Mock(file=mock_file_object),
            'course': str(self.course.id),
            'mode': 'asd',
        }
        response = self.client.post(reverse('norteamericanoapi:enroll'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("id=\"error_mode\"" in response._container[0].decode())

    @override_settings(REGISTRATION_EMAIL_PATTERNS_DISALLOWED=True)
    def test_generate_username(self):
        """
            Test username normal process
        """
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux1@test.ts'}).username,
            'aa_cc')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux2@test.ts'}).username,
            'aa_cc_d')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux3@test.ts'}).username,
            'aa_cc_dd')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux4@test.ts'}).username,
            'aa_b_cc')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux5@test.ts'}).username,
            'aa_bb_cc')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux6@test.ts'}).username,
            'aa_b_cc_d')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux7@test.ts'}).username,
            'aa_b_cc_dd')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux8@test.ts'}).username,
            'aa_bb_cc_d')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux9@test.ts'}).username,
            'aa_bb_cc_dd')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux10@test.ts'}).username,
            'aa_cc1')
        self.assertEqual(
            create_user_by_data({'names':'aa bb', 'lastnames':'cc dd','pass': '1234','email':'aux11@test.ts'}).username,
            'aa_cc2')

    @override_settings(REGISTRATION_EMAIL_PATTERNS_DISALLOWED=True)
    def test_long_name(self):
        """
            Test generate username long name
        """
        data = {
            'pass': '1234',
            'names': 'a2345678901234567890123 bb',
            'lastnames': '4567890 ff',
            'email': 'test@test.test'
        }

        self.assertEqual(create_user_by_data(
            data).username, 'a2345678901234567890123_41')

    @override_settings(REGISTRATION_EMAIL_PATTERNS_DISALLOWED=True)
    def test_whitespace_lastname(self):
        """
            Test generate username when lastname has too much whitespace
        """
        user_data = {
            'names': 'Name           Last    ',
            'lastnames': 'Last1          Last2      ',
            }
        self.assertEqual(
            generate_username(user_data),
            "name_last1")

    def test_enroll_csv_get(self):
        """
            test enroll user csv view GET method
        """
        response = self.client.get(reverse('norteamericanoapi:enroll'))
        self.assertEqual(response.status_code, 200)

        new_client = Client()
        response = new_client.get(reverse('norteamericanoapi:enroll'))
        self.assertEqual(response.status_code, 404)

class TestEnrollExportCSV(ModuleStoreTestCase):
    def setUp(self):
        super(TestEnrollExportCSV, self).setUp()
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.client.login(username='testuser3', password='12345')

    def test_enroll_export(self):
        """
            test export csv
        """
        response = self.client.get(reverse('norteamericanoapi:enroll-export'))
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['',"Email;Nombres;Apellidos\r\n"]
        self.assertEqual(data, expect)

        new_client = Client()
        response = new_client.get(reverse('norteamericanoapi:enroll-export'))
        self.assertEqual(response.status_code, 404)

    def test_enroll_export_post(self):
        """
            test export csv wrong method
        """
        response = self.client.post(reverse('norteamericanoapi:enroll-export'))
        self.assertEqual(response.status_code, 405)

class TestReRunPendingCourse(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunPendingCourse, self).setUp()
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
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
            # staff user
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.client.login(username='testuser3', password='12345')
            # user student
            self.student_client = Client()
            self.student = UserFactory(
                username='student',
                password='12345',
                email='student@edx.org')
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
        mongo_course1_id = self.course.id

        # rerun from mongo into split
        split_course3_id = CourseLocator(
            org="edx3", course="split3", run="rerun_test"
        )
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        CourseRerunState.objects.initiated(mongo_course1_id, split_course3_id, self.user, fields['display_name'])

        csv_reader.return_value = [
            [str(mongo_course1_id), str(split_course3_id), fields['display_name']]
            ]
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
        aux = '{};{};{};{}\r\n'.format(str(mongo_course1_id), str(split_course3_id), fields['display_name'], 'Procesandose')
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Estado\r\n', aux]
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
        csv_reader.return_value = [
            ['asdsadsad', str(split_course3_id), fields['display_name']]
            ]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        aux = '{};{};{};{}\r\n'.format('asdsadsad', str(split_course3_id), fields['display_name'], 'Formato del course_id incorrecto o el curso no existe')
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Estado\r\n', aux]
        self.assertEqual(data, expect)
    
    @patch('norteamericanoapi.views.file_to_csvreader')
    def test_rerun_wrong_new_course_id(self, csv_reader):
        """
            test rerun courses wwhen new course id is wrong
        """
        # Mark the action as initiated
        fields = {'display_name': 'rerun'}
        csv_reader.return_value = [
            [str(self.course.id), str(self.course.id), fields['display_name']]
            ]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        aux = '{};{};{};{}\r\n'.format(str(self.course.id), str(self.course.id), fields['display_name'], 'El nuevo course id ya existe o formato de course id incorrecto')
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Estado\r\n', aux]
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
        csv_reader.return_value = [
            [str(self.course.id), str(split_course3_id), fields['display_name']]
            ]
        mock_file_object = Mock()
        mock_file_object.configure_mock(name="file_name")
        post_data = {
            "file": Mock(file=mock_file_object),
        }
        response = self.student_client.post(reverse('norteamericanoapi:rerun'), post_data)
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        aux = '{};{};{};{}\r\n'.format(str(self.course.id), str(split_course3_id), fields['display_name'], 'Usuario no tiene permisos en el curso')
        expect = ['','Course Id;Nuevo Course Id;Nombre curso nuevo;Estado\r\n', aux]
        self.assertEqual(data, expect)

class TestReRunExportCSV(ModuleStoreTestCase):
    def setUp(self):
        super(TestReRunExportCSV, self).setUp()
        with patch('common.djangoapps.student.models.cc.User.save'):
            # staff user
            self.client = Client()
            self.user_staff = UserFactory(
                username='testuser3',
                password='12345',
                email='student2@edx.org',
                is_staff=True)
            self.client.login(username='testuser3', password='12345')

    def test_rerun_export(self):
        """
            test export rerun CSV file
        """
        response = self.client.get(reverse('norteamericanoapi:rerun-export'))
        self.assertEqual(response.status_code, 200)
        data = [x.decode() for x in response._container]
        expect = ['',"Course Id;Nuevo Course Id;Nombre curso nuevo\r\n"]
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
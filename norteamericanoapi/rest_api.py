#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from .views import NorteamericanoEnroll
from .serializers import EnrollSerializer, UnEnrollSerializer, ReRunPendingCourseSerializer, ReRunSerializer
from .email_tasks import enroll_email
from .utils import create_user_by_data, create_na_user, enroll_course_user, get_course_by_id
from common.djangoapps.course_action_state.models import CourseRerunState, CourseRerunUIStateManager
from cms.djangoapps.contentstore.views.course import rerun_course
from openedx.core.lib.api.authentication import BearerAuthentication
from datetime import datetime as dt
from rest_framework import permissions
from rest_framework import status
from opaque_keys.edx.keys import CourseKey
from opaque_keys import InvalidKeyError
import logging

logger = logging.getLogger(__name__)

try:
    from norteamericano_form.models import NAExtraInfo
    HAVE_NA_MODEL = True
except ImportError:
    HAVE_NA_MODEL = False

class EnrollApi(APIView):
    authentication_classes = (BearerAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, format=None):
        if HAVE_NA_MODEL is False:
            logger.error("NorteamericanoApiEnroll - Model is not installed")
            return Response({'error': "Model is not installed"}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.is_anonymous and request.user.has_perm('norteamericano_form.na_instructor_staff'):
            serializer = EnrollSerializer(data=request.data)
            if serializer.is_valid():
                login_url = 'https://{}/login'.format(settings.LMS_BASE)
                result = self.create_enroll_user(serializer.data, login_url)
                if result == 'success':
                    return Response(data={'result':'success'}, status=status.HTTP_200_OK)
                else:
                    return Response(data={'result':'error', 'error': result}, status=status.HTTP_200_OK)
            else:
                logger.error("NorteamericanoApiEnroll - serializer is not valid")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.error("NorteamericanoApiEnroll - User is Anonymous or dont have permission")
            return Response({'error': 'User dont have permission'}, status=status.HTTP_400_BAD_REQUEST)

    def create_enroll_user(self, data, login_url):
        with transaction.atomic():
            email = data['email'].lower()
            rut = data['rut']
            aux_pass = ''
            if NAExtraInfo.objects.filter(na_rut=rut).exists():
                na_user = NAExtraInfo.objects.get(na_rut=rut)
            else:
                try:
                    user = User.objects.get(email=email)
                    if NAExtraInfo.objects.filter(user=user).exists():
                        return 'EL correo esta asociado a otro rut'
                except User.DoesNotExist:
                    #create user
                    aux_pass = BaseUserManager().make_random_password(12)
                    aux_pass = aux_pass.lower()
                    user_data = {
                        'email':email,
                        'names':data['names'],
                        'lastnames': '{} {}'.format(data['lastname_1'], data['lastname_2']),
                        'pass': aux_pass
                    }
                    user = create_user_by_data(user_data)
                #create na_user
                datos = ['', data['lastname_1'], data['lastname_2'], data['names'], rut,data['birthday'], data['phone']]
                na_user = create_na_user(datos, user)
        #enroll and send email
        enroll_course_user(na_user.user, data['course'], data['mode'])
        course = get_course_by_id(CourseKey.from_string(data['course']))
        course_name = course.display_name_with_default
        emails_data = {
            'email':email,
            'user_name': na_user.user.profile.name.strip(),
            'password': aux_pass,
            'course_name': course_name
        }
        enroll_email.delay(emails_data, login_url)
        return 'success'

class UnenrollApi(APIView):
    authentication_classes = (BearerAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, format=None):
        if HAVE_NA_MODEL is False:
            logger.error("NorteamericanoApiUnenroll - Model is not installed")
            return Response({'error': "Model is not installed"}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.is_anonymous and request.user.has_perm('norteamericano_form.na_instructor_staff'):
            serializer = UnEnrollSerializer(data=request.data)
            if serializer.is_valid():
                self.unenroll_user(serializer.data)
                return Response(data={'result':'success'}, status=status.HTTP_200_OK)
            else:
                logger.error("NorteamericanoApiUnenroll - serializer is not valid")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.error("NorteamericanoApiUnenroll - User is Anonymous or dont have permission")
            return Response({'error': 'User dont have permission'}, status=status.HTTP_400_BAD_REQUEST)

    def unenroll_user(self, data):
        from common.djangoapps.student.models import CourseEnrollment, CourseEnrollmentAllowed
        course_id = data['course']
        course_key = CourseKey.from_string(course_id)
        rut = data['rut']
        with transaction.atomic():
            na_user = NAExtraInfo.objects.get(na_rut=rut)
            #unenroll CourseEnrollmentAllowed
            enrollmentAllowed = CourseEnrollmentAllowed.objects.filter(
                course_id=course_key, user__naextrainfo=na_user)
            if enrollmentAllowed:
                enrollmentAllowed.delete()
            #unenroll CourseEnrollment
            enrollment = CourseEnrollment.objects.filter(user__naextrainfo=na_user, course_id=course_key)
            if enrollment:
                enrollment.update(is_active=0)

class ReRunPendingCourseApi(APIView):
    authentication_classes = (BearerAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, format=None):
        if not request.user.is_anonymous and request.user.has_perm('norteamericano_form.na_instructor_staff'):
            serializer = ReRunPendingCourseSerializer(data=request.data)
            if serializer.is_valid():
                base_url = request.build_absolute_uri('/')
                pending_courses = self.pending_courses(serializer.data, base_url)
                return Response(data={'result':'success', 'courses_status':pending_courses}, status=status.HTTP_200_OK)
            else:
                logger.error("NorteamericanoReRunPendingCourse - serializer is not valid")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.error("NorteamericanoReRunPendingCourse - User is Anonymous or dont have permission")
            return Response({'error': 'User dont have permission'}, status=status.HTTP_400_BAD_REQUEST)

    def pending_courses(self, data, base_url):
        course_id = data['course']
        if course_id != 'all':
            course_key = CourseKey.from_string(course_id)
            aux = self.get_status_course(course_key)
            pending_courses = [ {'new_course_id':str(aux.course_key), 'origen_course_id': str(aux.source_course_key), 'display_name': aux.display_name, 'state': aux.state, 'new_course_url': '{}course/{}'.format(base_url,str(aux.course_key))} ]
        else:
            aux = self.get_all_courses_pending()
            pending_courses = [ {'new_course_id':str(x.course_key), 'origen_course_id': str(x.source_course_key), 'display_name': x.display_name, 'state': x.state, 'new_course_url': '{}course/{}'.format(base_url,str(x.course_key))} for x in aux ]
        
        return pending_courses
    
    def get_all_courses_pending(self):
        """
        Get all in-process course actions
        """
        return [
            course for course in
            CourseRerunState.objects.find_all(
                exclude_args={'state': CourseRerunUIStateManager.State.SUCCEEDED},
                should_display=True,
            )
        ]
    
    def get_status_course(self, course_key):
        return CourseRerunState.objects.get(
                course_key=course_key,
                should_display=True,
            )

class ReRunApi(APIView):
    authentication_classes = (BearerAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, format=None):
        if not request.user.is_anonymous and request.user.has_perm('norteamericano_form.na_instructor_staff'):
            serializer = ReRunSerializer(data=request.data)
            if serializer.is_valid():
                base_url = request.build_absolute_uri('/')
                response = self.rerun_courses(serializer.data, request.user, base_url)
                return Response(data=response, status=status.HTTP_200_OK)
            else:
                logger.error("NorteamericanoApiReRun - serializer is not valid")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.error("NorteamericanoApiReRun - User is Anonymous or dont have permission")
            return Response({'error': 'User dont have permission'}, status=status.HTTP_400_BAD_REQUEST)

    def rerun_courses(self, data, user, base_url):
        start_date = dt.strptime(data['start_date']+' +0000', "%H:%M %d/%m/%Y %z")
        end_date = dt.strptime(data['end_date']+' +0000', "%H:%M %d/%m/%Y %z")
        source_course_key = CourseKey.from_string(data['source_course'])
        new_course_key = CourseKey.from_string(data['new_course'])
        org = new_course_key.org
        number = new_course_key.course
        run = new_course_key.run
        fields = {'start': start_date, 'end':end_date, 'display_name':data['display_name']}
        wiki_slug = u"{0}.{1}.{2}".format(org, number, run)
        definition_data = {'wiki_slug': wiki_slug}
        fields.update(definition_data)
        try:
            new_course_id = rerun_course(user, source_course_key, org, number, run, fields)
        except Exception as e:
            logger.error('NorteamericanoApiReRun - Error in rerun_course(): {}'.format(str(e)))
            new_course_id = None
        if not new_course_id:
            result = 'Error en relanzar el curso'
            response = {'new_course_url':'', "status": 'Error en relanzar el curso','result':'error'}
        else:
            response = {'new_course_url':'{}course/{}'.format(base_url,str(new_course_id)), "status": 'Procesandose','result':'success'}
        return response

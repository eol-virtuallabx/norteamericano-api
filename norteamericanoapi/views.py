#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.generic.base import View
from django.http import HttpResponse
from .utils import file_to_csvreader, validate_course, validate_user, enroll_create_user_with_custom_fields, rerun_courses, HAVE_NA_MODEL
from .email_tasks import enroll_email
from common.djangoapps.edxmako.shortcuts import render_to_response
from cms.djangoapps.contentstore.views.course import get_in_process_course_actions
import logging
import json
import csv
from opaque_keys.edx.keys import CourseKey
from lms.djangoapps.courseware.courses import get_course_by_id
from common.djangoapps.util.json_request import JsonResponse, JsonResponseBadRequest

logger = logging.getLogger(__name__)

class NorteamericanoEnroll(View):
    """
        Enroll users
    """
    def get(self, request):
        if not request.user.is_anonymous:
            context = {'modo': 'honor', 'curso':'', 'HAVE_NA_MODEL': HAVE_NA_MODEL}
            return render_to_response('norteamericanoapi/enroll.html', context)
        else:
            logger.error("NorteamericanoEnroll - User is Anonymous")
        raise Http404()

    def post(self, request):
        """
            csv file first column is email
            [[email@email.com, lastnames_1, lastname_2, names, rut, birthday, phone],...]
        """
        context = {'result': 'success', 'modo': request.POST.get('mode', ''), 'curso':request.POST.get('course', ''), 'HAVE_NA_MODEL': HAVE_NA_MODEL}
        if HAVE_NA_MODEL is False:
            return render_to_response('norteamericanoapi/enroll.html', context)
        if not request.user.is_anonymous:
            error_response = self.validate_data(request)
            if len(error_response) > 0:
                context['result'] = 'error'
                context['errors'] = error_response
                return render_to_response('norteamericanoapi/enroll.html', context)
            csv_reader = file_to_csvreader(request.FILES.get('file').file)
            csv_data = [x for x in csv_reader]
            data = enroll_create_user_with_custom_fields(csv_data, request.POST.get('course'), request.POST.get('mode'))
            
            login_url = request.build_absolute_uri('/login')
            course = get_course_by_id(CourseKey.from_string(request.POST.get('course'))) 
            courses_name = course.display_name_with_default
            for email in data['emails_data']:
                enroll_email.delay(email, courses_name, login_url)

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="enroll_{}.csv"'.format(request.POST.get('course'))
            writer = csv.writer(
                response,
                delimiter=';',
                dialect='excel')
            writer.writerows(data['new_data'])
            return response
        else:
            logger.error("NorteamericanoEnroll - User is Anonymous")
            raise Http404()
    
    def validate_data(self, request):
        response = {}
        if request.FILES.get('file', None) is None or not hasattr(request.FILES.get('file'), "file"):
            logger.error('NorteamericanoEnroll - Error, request dont have csv file: {}'.format(request.POST))
            response['not_file'] = True
        if request.POST.get('course', '') == '':
            logger.error('NorteamericanoEnroll - Error, request dont have course_id: {}'.format(request.POST))
            response['not_course'] = True
        elif not validate_course(request.POST.get('course')):
            logger.error('NorteamericanoEnroll - Error, wrong course_id or dont exists, course_id: {}'.format(request.POST.get('course')))
            response['wrong_course'] = True
        elif not validate_user(request.user, request.POST.get('course')):
            response['error_permission'] = True
            logger.error("NorteamericanoEnroll - User dont have permission, user: {}, course_id: {}".format(request.user, request.POST.get('course')))
        if request.POST.get('mode', '') not in ['honor', 'audit']:
            response['error_mode'] = True
            logger.error("NorteamericanoEnroll - Wrong Mode, user: {}, mode: {}".format(request.user, request.POST.get('mode')))
        return response

class NorteamericanoEnrollExport(View):
    """
        Export CSV to enroll users
    """

    def get(self, request):
        if not request.user.is_anonymous:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="planilla_enroll.csv"'

            writer = csv.writer(
                response,
                delimiter=';',
                dialect='excel')
            writer.writerow(['Email', 'Apellido Paterno', 'Apellido Materno', 'Nombres', 'RUT', 'Fecha de Nacimiento', 'Fono'])
            return response
        else:
            logger.error("NorteamericanoEnrollExport - User is Anonymous")
        raise Http404()

class NorteamericanoReRunPendingCourse(View):
    """
        Get pending rerun courses
    """
    def get(self, request):
        if not request.user.is_anonymous:
            aux = get_in_process_course_actions(request)
            pending_courses = [ {'new_course_id':str(x.course_key), 'origen_course_id': str(x.source_course_key), 'display_name': x.display_name, 'state': x.state} for x in aux ]
            response = {'result': 'success', 'courses': pending_courses}
            return JsonResponse(response)
        else:
            logger.error("NorteamericanoReRunPendingCourse - User is Anonymous")
        raise Http404()

class NorteamericanoReRun(View):
    """
        Rerun courses from CSV
    """
    def get(self, request):
        if not request.user.is_anonymous:
            context = {'url_pending_courses': reverse("norteamericanoapi:pending-courses")}
            return render_to_response('norteamericanoapi/rerun.html', context)
        else:
            logger.error("NorteamericanoReRun - User is Anonymous")
        raise Http404()

    def post(self, request):
        context = {'result': 'success', 'url_pending_courses': reverse("norteamericanoapi:pending-courses")}
        if not request.user.is_anonymous:
            error_response = self.validate_data(request)
            if len(error_response) > 0:
                context['result'] = 'error'
                context['errors'] = error_response
                return render_to_response('norteamericanoapi/rerun.html', context)
            csv_reader = file_to_csvreader(request.FILES.get('file').file)
            csv_data = [x for x in csv_reader]
            data = rerun_courses(csv_data, request.user)
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="rerun_response.csv"'
            writer = csv.writer(
                response,
                delimiter=';',
                dialect='excel')
            writer.writerows(data)
            return response
        else:
            logger.error("NorteamericanoReRun - User is Anonymous")
            raise Http404()
    
    def validate_data(self, request):
        response = {}
        if request.FILES.get('file', None) is None or not hasattr(request.FILES.get('file'), "file"):
            logger.error('NorteamericanoReRun - Error, request dont have csv file: {}'.format(request.FILES))
            response['not_file'] = True
        return response

class NorteamericanoReRunExport(View):
    """
        Export CSV to rerun courses
    """

    def get(self, request):
        if not request.user.is_anonymous:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="planilla_rerun.csv"'

            writer = csv.writer(
                response,
                delimiter=';',
                dialect='excel')
            writer.writerow(['Course Id', 'Nuevo Course Id', 'Nombre curso nuevo'])
            return response
        else:
            logger.error("NorteamericanoReRunExport - User is Anonymous")
        raise Http404()
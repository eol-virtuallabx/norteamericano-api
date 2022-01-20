#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.generic.base import View
from django.http import HttpResponse
from .utils import validate_data, enroll_create_user_api
from .email_tasks import enroll_email
import logging
import json
from opaque_keys.edx.keys import CourseKey
from lms.djangoapps.courseware.courses import get_course_by_id
from common.djangoapps.util.json_request import JsonResponse, JsonResponseBadRequest

logger = logging.getLogger(__name__)


def enroll_users(request):
    # check method and params
    if request.method != "POST":
        logger.error("NorteamericanoAPI - Wrong method: {}".format(request.method))
        return HttpResponse(status=400)
    if request.user.is_anonymous:
        logger.error("NorteamericanoAPI - User is anonymous")
        return HttpResponse(status=400)
    if 'data' not in request.POST:
        logger.error("NorteamericanoAPI - No Data: {}".format(request.POST))
        return HttpResponse(status=400)
    try:
        data = json.loads(request.POST.get('data'))
    except Exception as e:
        logger.error("NorteamericanoAPI - data must be json format (json.dumps), user: {}, error: {}".format(request.user, str(e)))
        return HttpResponse(status=400)
    if 'user_data' not in data or 'course_ids' not in data or 'mode' not in data:
        logger.error("NorteamericanoAPI - Miss Data: {}".format(data))
        return HttpResponse(status=400)
    error_response = validate_data(request.user, data.get('user_data'), data.get('course_ids'), data.get('mode'))

    if len(error_response) > 0:
        return JsonResponse({'result': 'error', 'error': error_response})

    lista_saved = enroll_create_user_api(
        data.get('course_ids'), data.get('mode'), data.get('user_data'))

    login_url = request.build_absolute_uri('/login')
    #helpdesk_url = request.build_absolute_uri('/contact_form')
    list_course = data.get('course_ids')
    courses = [get_course_by_id(CourseKey.from_string(course_id)) for course_id in list_course]
    courses_name = ''
    for course in courses:
        courses_name = courses_name + course.display_name_with_default + ', '
    courses_name = courses_name[:-2]
    for email in lista_saved:
        enroll_email.delay(email, courses_name, login_url)

    return JsonResponse({'result': 'success'})

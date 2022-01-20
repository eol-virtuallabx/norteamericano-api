#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django.urls import reverse
from urllib.parse import urlencode
from itertools import cycle
from opaque_keys.edx.keys import CourseKey
from opaque_keys import InvalidKeyError
from lms.djangoapps.courseware.courses import get_course_by_id, get_course_with_access
from cms.djangoapps.contentstore.views.course import rerun_course
from xmodule.modulestore.django import modulestore
from common.djangoapps.student import auth
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from common.djangoapps.course_action_state.models import CourseRerunState
from xmodule.modulestore import EdxJSONEncoder
from xmodule.course_module import DEFAULT_START_DATE, CourseFields
from lms.djangoapps.courseware.access import has_access
import unidecode
import logging
import json
import six
import csv
import re
import io
from django.contrib.auth.base_user import BaseUserManager
logger = logging.getLogger(__name__)
regex = r'^(([^<>()\[\]\.,;:\s@\"]+(\.[^<>()\[\]\.,;:\s@\"]+)*)|(\".+\"))@(([^<>()[\]\.,;:\s@\"]+\.)+[^<>()[\]\.,;:\s@\"]{2,})$'
regex_names = r'^[A-Za-z\s\_]+$'
USERNAME_MAX_LENGTH = 30

def create_user_by_data(user_data, is_api=False):
    """
    Create the user by the Django model
    """
    from openedx.core.djangoapps.user_authn.views.registration_form import AccountCreationForm
    from common.djangoapps.student.helpers import do_create_account
    user_pass = user_data['pass']  # Temporary password
    form = AccountCreationForm(
        data={
            "username": generate_username(user_data),
            "email": user_data['email'],
            "password": user_pass,
            "name":  user_data['nombreCompleto'] if is_api else '{} {}'.format(user_data['names'], ['lastnames']),
        },
        tos_required=False,
        ignore_email_blacklist=True
    )
    user, _, reg = do_create_account(form)
    reg.activate()
    reg.save()
    #from common.djangoapps.student.models import create_comments_service_user
    #create_comments_service_user(user)

    return user

def generate_username(user_data, is_api=False):
        """
        Generate an username for the given user_data
        This generation will be done as follow:
        1. return first_name[0] + "_" + last_name[0]
        2. return first_name[0] + "_" + last_name[0] + "_" + last_name[1..N][0..N]
        3. return first_name[0] + "_" first_name[1..N][0..N] + "_" + last_name[0]
        4. return first_name[0] + "_" first_name[1..N][0..N] + "_" + last_name[1..N][0..N]
        5. return first_name[0] + "_" + last_name[0] + N
        """
        if is_api:
            aux_username = unidecode.unidecode(user_data['nombreCompleto'].lower())
            aux_username = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_username)
            aux_username = aux_username.split(" ")
            aux_username = [x for x in aux_username if x]
            if len(aux_username) > 1:
                i = int(len(aux_username)/2)
                aux_first_name = aux_username[0:i]
                aux_last_name = aux_username[i:]
            else:
                if User.objects.filter(username=aux_username[0]).exists():
                    for i in range(1, 10000):
                        name_tmp = aux_username[0] + str(i)
                        if not User.objects.filter(username=name_tmp).exists():
                            return name_tmp
                else:
                    return aux_username[0]
        else:
            aux_first_name = unidecode.unidecode(user_data['names'].lower())
            aux_first_name = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_first_name)
            aux_first_name = aux_first_name.split(" ")
            aux_first_name = [x for x in aux_first_name if x]
            aux_last_name = unidecode.unidecode(user_data['lastnames'].lower())
            aux_last_name = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_last_name)
            aux_last_name = aux_last_name.split(" ")
            aux_last_name = [x for x in aux_last_name if x]

        first_name = [x for x in aux_first_name if x != ''] or ['']
        last_name = [x for x in aux_last_name if x != ''] or ['']

        # 1.
        test_name = first_name[0] + "_" + last_name[0]
        if len(test_name) <= USERNAME_MAX_LENGTH and not User.objects.filter(
                username=test_name).exists():
            return test_name

        # 2.
        for i in range(len(last_name[1:])):
            test_name = test_name + "_"
            for j in range(len(last_name[i + 1])):
                test_name = test_name + last_name[i + 1][j]
                if len(test_name) > USERNAME_MAX_LENGTH:
                    break
                if not User.objects.filter(username=test_name).exists():
                    return test_name

        # 3.
        first_name_temp = first_name[0]
        for i in range(len(first_name[1:])):
            first_name_temp = first_name_temp + "_"
            for j in range(len(first_name[i + 1])):
                first_name_temp = first_name_temp + first_name[i + 1][j]
                test_name = first_name_temp + "_" + last_name[0]
                if len(test_name) > USERNAME_MAX_LENGTH:
                    break
                if not User.objects.filter(username=test_name).exists():
                    return test_name

        # 4.
        first_name_temp = first_name[0]
        for first_index in range(len(first_name[1:])):
            first_name_temp = first_name_temp + "_"
            for first_second_index in range(len(first_name[first_index + 1])):
                first_name_temp = first_name_temp + \
                    first_name[first_index + 1][first_second_index]
                test_name = first_name_temp + "_" + last_name[0]
                if len(test_name) > USERNAME_MAX_LENGTH:
                    break
                for second_index in range(len(last_name[1:])):
                    test_name = test_name + "_"
                    for second_second_index in range(
                            len(last_name[second_index + 1])):
                        test_name = test_name + \
                            last_name[second_index + 1][second_second_index]
                        if len(test_name) > USERNAME_MAX_LENGTH:
                            break
                        if not User.objects.filter(
                                username=test_name).exists():
                            return test_name

        # 5.
        # Make sure we have space to add the numbers in the username
        test_name = first_name[0] + "_" + last_name[0]
        test_name = test_name[0:(USERNAME_MAX_LENGTH - 5)]
        if test_name[-1] == '_':
            test_name = test_name[:-1]
        for i in range(1, 10000):
            name_tmp = test_name + str(i)
            if not User.objects.filter(username=name_tmp).exists():
                return name_tmp

        # Username cant be generated
        raise Exception("Error generating username for name {}".format())

def validate_course(id_curso):
    """
        Verify if course.id exists
    """
    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
    try:
        aux = CourseKey.from_string(id_curso)
        return CourseOverview.objects.filter(id=aux).exists()
    except InvalidKeyError:
        logger.error("Norteamericano error valdiate course, invalid format: {}".format(id_curso))
        return False

def is_course_staff(user, course_id):
    """
        Verify if the user is staff course
    """
    try:
        course_key = CourseKey.from_string(course_id)
        course = get_course_with_access(user, "load", course_key)

        return bool(has_access(user, 'staff', course))
    except Exception:
        return False

def is_instructor(user, course_id):
    """
        Verify if the user is instructor
    """
    try:
        course_key = CourseKey.from_string(course_id)
        course = get_course_with_access(user, "load", course_key)

        return bool(has_access(user, 'instructor', course))
    except Exception:
        return False

def validate_user(user, course_id):
    """
        Verify if the user have permission
    """
    access = False
    if not user.is_anonymous:
        if user.is_staff:
            access = True
        if is_instructor(user, course_id):
            access = True
        if is_course_staff(user, course_id):
            access = True
    return access

def validate_data(user, lista_data, course_ids, mode):
    """
        Validate Data enroll users
    """
    response = {}
    wrong_data = []
    duplicate_data = []
    original_data = []
    duplicate_courses = []
    original_courses = []
    # si no se ingreso datos
    if not lista_data:
        logger.error("NorteamericanoAPI - Empty Data, user: {}".format(user.id))
        response['empty_data'] = True
    elif type(lista_data) != list:
        logger.error("NorteamericanoAPI - error data users, user: {}".format(user.id))
        response['error_type_users'] = True
    else:
        for data in lista_data:
            try:
                if len(data) != 2:
                    wrong_data.append(data)
                    logger.error("NorteamericanoAPI - Wrong Data, parameters length != 2, user: {}, wrong_data: {}".format(user.id, data))
                else:
                    if data[0] != "" and data[1] != "":
                        aux_name = unidecode.unidecode(data[0].lower())
                        #aux_name = re.sub(r'[^a-zA-Z0-9\_]', ' ', aux_name)
                        if not re.match(regex_names, aux_name):
                            logger.error("NorteamericanoAPI - Wrong Name, not allowed specials characters, user: {}, wrong_data: {}".format(user.id, data))
                            wrong_data.append(data)
                        elif not re.match(regex, data[1].lower()):
                            logger.error("NorteamericanoAPI - Wrong Email {}, user: {}, wrong_data: {}".format(data[1].lower(), user.id, data))
                            wrong_data.append(data)
                        elif data[1] in original_data:
                            duplicate_data.append(data[1])
                        else:
                            original_data.append(data[1])
                    else:
                        wrong_data.append(data)
            except TypeError as e:
                wrong_data.append(data)
                logger.error("NorteamericanoAPI - TypeError Data, user: {}, wrong_data: {}".format(user.id, data))
    if len(wrong_data) > 0:
        logger.error("NorteamericanoAPI - Wrong Data, user: {}, wrong_data: {}".format(user.id, wrong_data))
        response['wrong_data'] = wrong_data
    if len(duplicate_data) > 0:
        logger.error("NorteamericanoAPI - Duplicate Email, user: {}, duplicate_data: {}".format(user.id, duplicate_data))
        response['duplicate_email'] = duplicate_data
    # valida curso
    if len(course_ids) == 0:
        logger.error("NorteamericanoAPI - Empty course, user: {}".format(user.id))
        response['empty_course'] = True
    elif type(course_ids) != list:
        logger.error("NorteamericanoAPI - error data course, user: {}".format(user.id))
        response['error_type_course'] = True
    # valida si existe el curso
    else:
        for course_id in course_ids:
            if course_id in original_courses:
                duplicate_courses.append(course_id)
            else:
                original_courses.append(course_id)
            if not validate_course(course_id):
                if 'error_curso' not in response:
                    response['error_curso'] = [course_id]
                else:
                    response['error_curso'].append(course_id)
                logger.error("NorteamericanoAPI - Course dont exists, user: {}, course_id: {}".format(user.id, course_id))
        if 'error_curso' not in response:
            for course_id in course_ids:
                if not validate_user(user, course_id):
                    if 'error_permission' not in response:
                        response['error_permission'] = [course_id]
                    else:
                        response['error_permission'].append(course_id)
                    logger.error("NorteamericanoAPI - User dont have permission, user: {}, course_id: {}".format(user.id, course_id))
    if len(duplicate_courses) > 0:
        response['duplicate_courses'] = duplicate_courses
    # si el modo es incorrecto
    if mode not in ['honor', 'audit']:
        response['error_mode'] = True
        logger.error("NorteamericanoAPI - Wrong Mode, user: {}, mode: {}".format(user.id, mode))
    return response

def enroll_create_user_api(course_ids, mode, lista_data):
    """
        Create and enroll the user from api
    """
    lista_saved = []
    # guarda el form
    with transaction.atomic():
        for dato in lista_data:
            dato = [d.strip() for d in dato]
            dato[1] = dato[1].lower()
            aux_pass = ''
            aux_user = False
            try:
                user = User.objects.get(email=aux_email)
                aux_user = True
            except User.DoesNotExist:
                aux_pass = BaseUserManager().make_random_password(12).lower()
                user_data = {
                    'email':dato[1],
                    'nombreCompleto':dato[0],
                    'pass': aux_pass
                }
                user = create_user_by_data(user_data)
            for course_id in course_ids:
                enroll_course_user(user, course_id, mode)
            lista_saved.append({
                'email': dato[1],
                'user_name': user.profile.name.strip(),
                'password': aux_pass,
                'exists': aux_user
            })
    return lista_saved

def enroll_course_user(user, course, mode):
    """
        Enroll the user in the course.
    """
    from common.djangoapps.student.models import CourseEnrollment
    CourseEnrollment.enroll(
        user,
        CourseKey.from_string(course),
        mode=mode)

def file_to_csvreader(csvfile):
    """
        Convert file in csv object
    """
    package_file = csvfile
    decoded_file = package_file.read().decode('utf-8')
    io_string = io.StringIO(decoded_file)
    csv_reader = csv.reader(io_string, delimiter=';')
    header = next(csv_reader)
    return csv_reader

def enroll_create_user(csv_data, course_id, mode):
    """
        Create and enroll the user
    """
    new_data = [['Email', 'Nombres', 'Apellidos', 'Username', 'Estado']]
    emails_data = []
    with transaction.atomic():
        for row in csv_data:
            row[0] = row[0].lower()
            aux_pass = ''
            aux_user = False
            try:
                user = User.objects.get(email=row[0])
                aux_user = True
            except User.DoesNotExist:
                if re.match(regex, row[0]):
                    aux_pass = BaseUserManager().make_random_password(12).lower()
                    user_data = {
                        'email':row[0],
                        'names':row[1],
                        'lastnames':row[2],
                        'pass': aux_pass
                    }
                    user = create_user_by_data(user_data)
                else:
                    user = None
            if user:
                enroll_course_user(user, course_id, mode)
                new_data.append([
                    row[0],row[1],row[2],
                    user.username,
                    'Inscrito' if aux_user else 'Creado e Inscrito'
                ])
                emails_data.append({
                    'email':row[0],
                    'user_name': user.profile.name.strip(),
                    'password': aux_pass,
                    'exists': aux_user
                })
            else:
                aux_row = ['','','','','Error, Revise los datos si estan correctos']
                if len(row) < 5:
                    new_data.append(row + aux_row[len(row):])
                else:
                    new_data.append(row[:4] + [aux_row[-1]])
    return {'new_data': new_data, 'emails_data': emails_data}

def rerun_courses(csv_data, user):
    """
        ReRun Courses from CSV file
    """
    new_data = [['Course Id', 'Nuevo Course Id', 'Nombre curso nuevo', 'Estado']]
    for course_ids in csv_data:
        if not validate_course(course_ids[0]):
            new_data.append([course_ids[0], course_ids[1], course_ids[2], 'Formato del course_id incorrecto o el curso no existe'])
        elif validate_course(course_ids[1]):
            new_data.append([course_ids[0], course_ids[1], course_ids[2],'El nuevo course id ya existe o formato de course id incorrecto'])
        elif not validate_user(user, course_ids[0]):
            new_data.append([course_ids[0], course_ids[1], course_ids[2],'Usuario no tiene permisos en el curso'])
        else:
            new_course_key = CourseKey.from_string(course_ids[1])
            org = new_course_key.org
            number = new_course_key.course
            run = new_course_key.run
            display_name = course_ids[2]
            start = CourseFields.start.default
            fields = {'start': start}
            if display_name:
                fields['display_name'] = display_name

            wiki_slug = u"{0}.{1}.{2}".format(org, number, run)
            definition_data = {'wiki_slug': wiki_slug}
            fields.update(definition_data)

            source_course_key = CourseKey.from_string(course_ids[0])
            try:
                new_course_id = rerun_course(user, source_course_key, org, number, run, fields)
            except Exception as e:
                logger.error('NorteamericanoReRun - Error in rerun_course(): {}'.format(str(e)))
                new_course_id = None
            aux_data = [course_ids[0], course_ids[1], course_ids[2],'Procesandose']
            if not new_course_id:
                aux_data[-1] = 'Error en relanzar el curso'
            new_data.append(aux_data)
    return new_data

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
from xmodule.modulestore.django import modulestore
from common.djangoapps.student import auth
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from common.djangoapps.course_action_state.models import CourseRerunState
from xmodule.modulestore import EdxJSONEncoder
from xmodule.course_module import DEFAULT_START_DATE, CourseFields
from openedx.core.djangoapps.models.course_details import CourseDetails
from lms.djangoapps.courseware.access import has_access
from datetime import datetime as dt
import unidecode
import logging
import json
import six
import csv
import re
import io
from django.contrib.auth.base_user import BaseUserManager
try:
    from norteamericano_form.models import NAExtraInfo
    HAVE_NA_MODEL = True
except ImportError:
    HAVE_NA_MODEL = False
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

def validate_course_pending_course(course_id):
    """
        Validate if course id exists in pending rerun
    """
    from common.djangoapps.course_action_state.models import CourseRerunState
    try:
        aux = CourseKey.from_string(course_id)
        return CourseRerunState.objects.filter(course_key=aux).exists()
    except InvalidKeyError:
        logger.error("Norteamericano error validate_course_pending_course, invalid format: {}".format(course_id))
        return False

def set_data_course(course_key, start_date, end_date, user):
    """
        Set start_date and/or end_date
    """
    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
    with transaction.atomic():
        course = CourseOverview.objects.get(id=course_key)
        data = {}
        if start_date:
            start = dt.strptime(start_date+' +0000', "%H:%M %d/%m/%Y %z")
            data['start_date'] = start.strftime("%Y-%m-%dT%H:%M:%S")+'Z'
        else:
            start = course.start_date
        if end_date:
            end = dt.strptime(end_date+' +0000', "%H:%M %d/%m/%Y %z")
            data['end_date'] = end.strftime("%Y-%m-%dT%H:%M:%S")+'Z'
        else:
            end = course.end_date
        if end <= start:
            return False
        if data:
            data['intro_video'] = CourseDetails.fetch_youtube_video_id(course_key)
            CourseDetails.update_from_json(course_key, data, user)
        return True

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
    if not user.is_anonymous and user.has_perm('norteamericano_form.na_instructor_staff'):
        if user.is_staff:
            access = True
        if is_instructor(user, course_id):
            access = True
        if is_course_staff(user, course_id):
            access = True
    return access

def enroll_course_user(user, course, mode):
    """
        Enroll the user in the course.
    """
    from common.djangoapps.student.models import CourseEnrollment
    CourseEnrollment.enroll(
        user,
        CourseKey.from_string(course),
        mode=mode)

def add_role_course_staff(user, course_key):
    """
        Add instructor role
    """
    role = CourseInstructorRole(course_key)
    role.add_users(user)

def remove_role_course_staff(user, course_key):
    """
        Remove instructor role
    """
    role = CourseInstructorRole(course_key)
    role.remove_users(user)

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

def enroll_create_user_with_custom_fields(csv_data, mode):
    """
        Create and enroll the user
    """
    new_data = [['Email', 'Apellido Paterno', 'Apellido Materno', 'Nombres', 'RUT', 'Fecha de Nacimiento', 'Fono', 'Id curso', 'Username', 'Estado']]
    emails_data = []
    courses = {}
    with transaction.atomic():
        for row in csv_data:
            if len(row) < 8:
                while len(row) < 8:
                    row.append('')
                new_data.append(row + ['', 'Faltan datos'])
                continue
            elif len(row) < 10:
                while len(row) < 10:
                    row.append('')

            row[0] = row[0].lower()
            row[4] = row[4].upper()
            row[4] = row[4].replace("-", "")
            row[4] = row[4].replace(".", "")
            row[4] = row[4].strip()
            aux_pass = ''
            error = ''
            user_created = False
            if not validarRutAllType(row[4]):
                row[-1] = 'Rut/Pasaporte invalido'
                new_data.append(row)
                continue
            if row[4][0] != 'P':
                row[4] = '{}-{}'.format(row[4][:-1], row[4][-1])
            if not validate_course(row[7]):
                row[-1] = 'Id curso invalido o curso no existe'
                new_data.append(row)
                continue
            if NAExtraInfo.objects.filter(na_rut=row[4]).exists():
                na_user = NAExtraInfo.objects.get(na_rut=row[4])
            else:
                try:
                    user = User.objects.get(email=row[0])
                    if NAExtraInfo.objects.filter(user=user).exists():
                        user = None
                        error = 'EL correo esta asociado a otro rut'
                except User.DoesNotExist:
                    if re.match(regex, row[0]):
                        aux_pass = BaseUserManager().make_random_password(12)
                        aux_pass = aux_pass.lower()
                        user_data = {
                            'email':row[0],
                            'names':row[3],
                            'lastnames': '{} {}'.format(row[1], row[2]),
                            'pass': aux_pass
                        }
                        user = create_user_by_data(user_data)
                        user_created = True
                    else:
                        user = None
                        error = 'Formato del correo incorrecto'
                if user:
                    na_user = create_na_user(row, user)
                else:
                    na_user = None
            if na_user:
                enroll_course_user(na_user.user, row[7], mode)
                row[-2] = na_user.user.username
                row[-1] = 'Inscrito' if aux_pass == '' else 'Creado e Inscrito'
                new_data.append(row)
                if row[7] in courses:
                    course_name = courses[row[7]]
                else:
                    course = get_course_by_id(CourseKey.from_string(row[7]))
                    course_name = course.display_name_with_default
                    courses[row[7]] = course_name
                emails_data.append({
                    'email':row[0],
                    'user_name': na_user.user.profile.name.strip(),
                    'password': aux_pass,
                    'course_name': course_name
                })
            else:
                row[-1] = error
                new_data.append(row)
    return {'new_data': new_data, 'emails_data': emails_data}

def create_na_user(user_data, user):
    """
        Create the user given the user data.
    """
    with transaction.atomic():
        na_user = NAExtraInfo.objects.create(
            user=user,
            na_names=user_data[3],
            na_lastname_p=user_data[1],
            na_lastname_m=user_data[2],
            na_rut=user_data[4],
            na_birth_date=user_data[5],
            na_phone=user_data[6]
        )
    return na_user

def rerun_courses(csv_data, user):
    """
        ReRun Courses from CSV file
    """
    from cms.djangoapps.contentstore.views.course import rerun_course
    new_data = [['Course Id', 'Nuevo Course Id', 'Nombre curso nuevo', 'Fecha de Inicio(UTC)', 'Fecha de Termino(UTC)', 'Estado']]
    for course_ids in csv_data:
        if len(course_ids) < 5:
            while len(course_ids) < 5:
                course_ids.append('')
            new_data.append(course_ids + ['Faltan datos'])
            continue
        if len(course_ids) < 6:
            course_ids.append('')
        try:
            aux = CourseKey.from_string(course_ids[1])
        except InvalidKeyError:
            logger.error("Norteamericano error format course_id, invalid format: {}".format(course_ids[1]))
            course_ids[5] = 'Formato del nuevo course_id incorrecto'
            new_data.append(course_ids)
            continue
        if not validate_course(course_ids[0]):
            course_ids[5] = 'Formato del course_id incorrecto o el curso no existe'
            new_data.append(course_ids)
        elif validate_course(course_ids[1]):
            course_ids[5] = 'El nuevo course id ya existe'
            new_data.append(course_ids)
        elif not validate_user(user, course_ids[0]):
            course_ids[5] = 'Usuario no tiene permisos en el curso'
            new_data.append(course_ids)
        else:
            try:
                start_date = dt.strptime(course_ids[3]+' +0000', "%H:%M %d/%m/%Y %z")
                end_date = dt.strptime(course_ids[4]+' +0000', "%H:%M %d/%m/%Y %z")
            except ValueError:
                course_ids[5] = 'Formato incorrecto en las fechas del curso'
                new_data.append(course_ids)
                continue
            new_course_key = CourseKey.from_string(course_ids[1])
            org = new_course_key.org
            number = new_course_key.course
            run = new_course_key.run
            display_name = course_ids[2]
            fields = {'start': start_date, 'end':end_date}
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
            course_ids[5] = 'Procesandose'
            if not new_course_id:
                course_ids[5] = 'Error en relanzar el curso'
            new_data.append(course_ids)
    return new_data

def validarRut(rut):
    """
        Verify if the 'rut' is valid
    """
    rut = rut.upper()
    rut = rut.replace("-", "")
    rut = rut.replace(".", "")
    rut = rut.strip()
    aux = rut[:-1]
    dv = rut[-1:]

    revertido = list(map(int, reversed(str(aux))))
    factors = cycle(list(range(2, 8)))
    s = sum(d * f for d, f in zip(revertido, factors))
    res = (-s) % 11

    if str(res) == dv:
        return True
    elif dv == "K" and res == 10:
        return True
    else:
        return False

def validarRutAllType(run):
    """
        Validate all Rut types
    """
    try:
        if run[0] == 'P':
            if 5 > len(run[1:]) or len(run[1:]) > 20:
                logger.error("NorteamericanoAPI - Rut Passport wrong, rut".format(run))
                return False
        else:
            if not validarRut(run):
                logger.error("NorteamericanoAPI - Rut wrong, rut".format(run))
                return False

    except Exception:
        logger.error("NorteamericanoAPI - Rut wrong, rut".format(run))
        return False

    return True
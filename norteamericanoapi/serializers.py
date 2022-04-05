from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from opaque_keys import InvalidKeyError
from rest_framework import serializers
from .utils import validarRutAllType, validate_course_pending_course
from .utils import validate_course as utils_validate_course
from norteamericano_form.models import NAExtraInfo
from datetime import datetime as dt
from openedx.core.djangoapps.course_groups.cohorts import is_cohort_exists
import re
import logging
logger = logging.getLogger(__name__)
regex = r'^(([^<>()\[\]\.,;:\s@\"]+(\.[^<>()\[\]\.,;:\s@\"]+)*)|(\".+\"))@(([^<>()[\]\.,;:\s@\"]+\.)+[^<>()[\]\.,;:\s@\"]{2,})$'

class EnrollSerializer(serializers.Serializer):
    email = serializers.CharField(required=True, allow_blank=False)
    lastname_1 =serializers.CharField(required=True, allow_blank=False)
    lastname_2 =serializers.CharField(required=True, allow_blank=True)
    names =serializers.CharField(required=True, allow_blank=False)
    rut =serializers.CharField(required=True, allow_blank=False)
    birthday =serializers.CharField(required=True)
    phone =serializers.CharField(required=True)
    course =serializers.CharField(required=True, allow_blank=False)
    mode =serializers.ChoiceField(
        choices=(
            ('honor', 'honor'),
            ('audit', 'audit')
        ),
        required=True
    )

    def validate_course(self, value):
        course = value
        if not utils_validate_course(course):
            logger.error('NAEnrollSerializer - Course key not valid or dont exists: {}'.format(course))
            raise serializers.ValidationError(u"Course key not valid or dont exists: {}".format(course))
        return course

    def validate_rut(self, value):
        rut = value
        if not validarRutAllType(rut):
            logger.error("NAEnrollSerializer - 'Rut/Passport invalid': {}".format(rut))
            raise serializers.ValidationError(u"'Rut/Passport invalid': {}".format(rut))
        rut = rut.upper()
        rut = rut.replace("-", "")
        rut = rut.replace(".", "")
        rut = rut.strip()
        if rut[0] != 'P':
            rut = '{}-{}'.format(rut[:-1], rut[-1])
        return rut
    
    def validate_email(self, value):
        email = value
        if not re.match(regex, email):
            logger.error("NAEnrollSerializer - 'Email invalid': {}".format(email))
            raise serializers.ValidationError(u"'Email invalid': {}".format(email))
        return email

class UnEnrollSerializer(serializers.Serializer):
    rut =serializers.CharField(required=True)
    course =serializers.CharField(required=True)

    def validate_rut(self, value):
        rut = value
        if not validarRutAllType(rut):
            logger.error("NAUnEnrollSerializer - 'Rut/Passport invalid': {}".format(rut))
            raise serializers.ValidationError(u"'Rut/Passport invalid': {}".format(rut))
        rut = rut.upper()
        rut = rut.replace("-", "")
        rut = rut.replace(".", "")
        rut = rut.strip()
        if rut[0] != 'P':
            rut = '{}-{}'.format(rut[:-1], rut[-1])
        if not NAExtraInfo.objects.filter(na_rut=rut).exists():
            logger.error("NAUnEnrollSerializer - 'Rut/Passport is not registered': {}".format(rut))
            raise serializers.ValidationError(u"'Rut/Passport is not registered': {}".format(rut))
        return rut

    def validate_course(self, value):
        course = value
        if not utils_validate_course(course):
            logger.error('NAUnEnrollSerializer - Course key not valid or dont exists: {}'.format(course))
            raise serializers.ValidationError(u"Course key not valid or dont exists: {}".format(course))
        return course

class ReRunPendingCourseSerializer(serializers.Serializer):
    course =serializers.CharField(required=True)

    def validate_course(self, value):
        course = value
        if course == 'all':
            return course
        if not validate_course_pending_course(course):
            logger.error('NAReRunPendingCourseSerializer - Course key not valid or dont exists: {}'.format(course))
            raise serializers.ValidationError(u"Course key not valid or dont exists: {}".format(course))
        return course

class ReRunSerializer(serializers.Serializer):
    source_course =serializers.CharField(required=True, allow_blank=False)
    new_course =serializers.CharField(required=True, allow_blank=False)
    display_name =serializers.CharField(required=True, allow_blank=False)
    start_date =serializers.CharField(required=True, allow_blank=False)
    end_date =serializers.CharField(required=True, allow_blank=False)

    def validate_source_course(self, value):
        course = value
        if not utils_validate_course(course):
            logger.error('NAReRunSerializer - Source Course key not valid or dont exists: {}'.format(course))
            raise serializers.ValidationError(u"Source Course key not valid or dont exists: {}".format(course))
        return course

    def validate_new_course(self, value):
        course = value
        try:
            aux = CourseKey.from_string(course)
        except InvalidKeyError:
            logger.error('NAReRunSerializer - New Course key not valid: {}'.format(course))
            raise serializers.ValidationError(u"New Course key not valid: {}".format(course))
        if utils_validate_course(course):
            raise serializers.ValidationError(u"New Course key already exists: {}".format(course))
        return course
    
    def validate_start_date(self, value):
        start_date = value
        try:
            aux = dt.strptime(start_date+' +0000', "%H:%M %d/%m/%Y %z")
        except ValueError:
            logger.error('NAReRunSerializer - Wrong format start_date: {}, must be HH:MM DD/MM/YYYY'.format(start_date))
            raise serializers.ValidationError(u"Wrong format start_date: {}, must be 'HH:MM DD/MM/YYYY'".format(start_date))
        return start_date
    
    def validate_end_date(self, value):
        end_date = value
        try:
            aux = dt.strptime(end_date+' +0000', "%H:%M %d/%m/%Y %z")
        except ValueError:
            logger.error('NAReRunSerializer - Wrong format end_date: {}, must be HH:MM DD/MM/YYYY'.format(end_date))
            raise serializers.ValidationError(u"Wrong format end_date: {}, must be 'HH:MM DD/MM/YYYY'".format(end_date))
        return end_date

    def validate(self, attrs):
        try:
            start_date = dt.strptime(attrs.get('start_date', '')+' +0000', "%H:%M %d/%m/%Y %z")
            end_date = dt.strptime(attrs.get('end_date', '')+' +0000', "%H:%M %d/%m/%Y %z")
            if end_date <= start_date:
                logger.error('NAReRunSerializer - end_date must be later than the start_date.')
                raise serializers.ValidationError(u"end_date must be later than the start_date.")
        except ValueError:
            logger.error('NAReRunSerializer - Wrong format date, must be HH:MM DD/MM/YYYY')
            raise serializers.ValidationError(u"Wrong format date, must be 'HH:MM DD/MM/YYYY'")
        return attrs
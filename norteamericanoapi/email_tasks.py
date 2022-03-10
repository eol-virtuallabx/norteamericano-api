
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
from django.conf import settings

from celery import task
from django.core.mail import send_mail
from django.utils.html import strip_tags

from django.template.loader import render_to_string

import logging
logger = logging.getLogger(__name__)

EMAIL_DEFAULT_RETRY_DELAY = 30
EMAIL_MAX_RETRIES = 5

@task(
    queue='edx.lms.core.low',
    default_retry_delay=EMAIL_DEFAULT_RETRY_DELAY,
    max_retries=EMAIL_MAX_RETRIES)
def enroll_email(data, login_url):
    """
        Send mail to specific user
    """
    platform_name = configuration_helpers.get_value(
            'PLATFORM_NAME', settings.PLATFORM_NAME)
    subject = 'Inscripción en el curso: {}'.format(data['course_name'])
    context = {
        "course_name": data['course_name'],
        "platform_name": platform_name,
        "user_password": data['password'],
        'user_email': data['email'],
        'login_url': login_url,
        'user_name': data['user_name']
    }
    if data['password'] != '':
        html_message = render_to_string('emails/exists_user_email.txt', context)
    else:
        html_message = render_to_string('emails/normal_email.txt', context)
    plain_message = strip_tags(html_message)
    from_email = configuration_helpers.get_value(
        'email_from_address',
        settings.BULK_EMAIL_DEFAULT_FROM_EMAIL
    )
    mail = send_mail(
        subject,
        plain_message,
        from_email,
        [data['email']],
        fail_silently=False,
        html_message=html_message)
    return mail
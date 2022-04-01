from django.contrib import admin
from django.conf.urls import url
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .views import *
from .rest_api import EnrollApi, UnenrollApi, ReRunPendingCourseApi, ReRunApi


urlpatterns = [
    url('enroll/', NorteamericanoEnroll.as_view(), name='enroll'),
    url('apiv1/', EnrollApi.as_view(), name='enroll-api'),
    url('apiv2/', UnenrollApi.as_view(), name='unenroll-api'),
    url('apiv3/', ReRunPendingCourseApi.as_view(), name='pending-courses-api'),
    url('apiv4/', ReRunApi.as_view(), name='rerun-api'),
    url('enroll-export/', NorteamericanoEnrollExport.as_view(), name='enroll-export'),
    url('rerun/', NorteamericanoReRun.as_view(), name='rerun'),
    url('rerun-export/', NorteamericanoReRunExport.as_view(), name='rerun-export'),
    url('pending-courses/', NorteamericanoReRunPendingCourse.as_view(), name='pending-courses'),
]

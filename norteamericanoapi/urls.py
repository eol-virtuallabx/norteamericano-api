from django.contrib import admin
from django.conf.urls import url
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .views import *
from .rest_api import EnrollApi, UnenrollApi, ReRunPendingCourseApi, ReRunApi


urlpatterns = [
    url(r'^api/v0/pending-courses/$', ReRunPendingCourseApi.as_view(), name='pending-courses-api'),
    url(r'^api/v0/rerun/$', ReRunApi.as_view(), name='rerun-api'),
    url(r'^rerun/$', NorteamericanoReRun.as_view(), name='rerun'),
    url(r'^rerun-export/$', NorteamericanoReRunExport.as_view(), name='rerun-export'),
    url(r'^pending-courses/$', NorteamericanoReRunPendingCourse.as_view(), name='pending-courses'),
]

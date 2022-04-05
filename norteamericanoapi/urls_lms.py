from django.contrib import admin
from django.conf.urls import url
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .views import *
from .rest_api import EnrollApi, UnenrollApi, ReRunPendingCourseApi, ReRunApi


urlpatterns = [
    url(r'^enroll/$', NorteamericanoEnroll.as_view(), name='enroll'),
    url(r'^api/v0/enroll/$', EnrollApi.as_view(), name='enroll-api'),
    url(r'^api/v0/unenroll/$', UnenrollApi.as_view(), name='unenroll-api'),
    url(r'^enroll-export/$', NorteamericanoEnrollExport.as_view(), name='enroll-export'),
]

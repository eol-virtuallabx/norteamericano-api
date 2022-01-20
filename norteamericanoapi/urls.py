from django.contrib import admin
from django.conf.urls import url
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from .views import *


urlpatterns = [
    url('enroll/', NorteamericanoEnroll.as_view(), name='enroll'),
    url('enroll-export/', NorteamericanoEnrollExport.as_view(), name='enroll-export'),
    url('rerun/', NorteamericanoReRun.as_view(), name='rerun'),
    url('rerun-export/', NorteamericanoReRunExport.as_view(), name='rerun-export'),
    url('pending-courses/', NorteamericanoReRunPendingCourse.as_view(), name='pending-courses'),
]

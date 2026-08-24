from django.contrib import admin

from .models import DriftMonitor, DriftRun

admin.site.register(DriftMonitor)
admin.site.register(DriftRun)

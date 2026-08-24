from django.contrib import admin

from .models import EventOutbox

admin.site.register(EventOutbox)

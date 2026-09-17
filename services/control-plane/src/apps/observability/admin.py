from django.contrib import admin

from .models import EventOutbox, LifecycleEvent

admin.site.register(EventOutbox)
admin.site.register(LifecycleEvent)

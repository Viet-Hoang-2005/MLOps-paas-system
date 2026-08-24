from django.contrib import admin

from .models import TrainingJob, TrainingJobEvent, TrainingOutput

admin.site.register(TrainingJob)
admin.site.register(TrainingJobEvent)
admin.site.register(TrainingOutput)

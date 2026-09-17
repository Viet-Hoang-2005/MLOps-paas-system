from django.contrib import admin

from .models import TrainingJob, TrainingOutput

admin.site.register(TrainingJob)
admin.site.register(TrainingOutput)

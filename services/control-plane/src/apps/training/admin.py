from django.contrib import admin

from .models import TrainingJob, TrainingOutput, TrainingWorkspace

admin.site.register(TrainingJob)
admin.site.register(TrainingOutput)
admin.site.register(TrainingWorkspace)

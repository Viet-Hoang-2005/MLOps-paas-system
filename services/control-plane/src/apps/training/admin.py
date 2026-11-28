from django.contrib import admin

from apps.training.jobs.models import TrainingJob
from apps.training.outputs.models import TrainingOutput
from apps.training.workspace.models import TrainingWorkspace

admin.site.register(TrainingJob)
admin.site.register(TrainingOutput)
admin.site.register(TrainingWorkspace)

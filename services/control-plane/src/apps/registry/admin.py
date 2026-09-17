from django.contrib import admin

from .models import ModelArtifact, ModelMetric, ModelVersion, RegistryAlias

admin.site.register(ModelVersion)
admin.site.register(ModelArtifact)
admin.site.register(ModelMetric)
admin.site.register(RegistryAlias)

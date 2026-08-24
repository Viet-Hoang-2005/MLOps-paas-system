from django.contrib import admin

from .models import Build, BuildInputAsset, Deployment, Endpoint

admin.site.register(Build)
admin.site.register(BuildInputAsset)
admin.site.register(Deployment)
admin.site.register(Endpoint)

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.projects.selectors import project_for_user


class RunningSourceEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.running.snapshots import running_source

        project = project_for_user(request.user, project_id)
        version_id = request.query_params.get("version_id")
        return Response({"content": running_source(project, version_id=version_id)})


class RunningAttributesEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.running.snapshots import running_attributes

        project = project_for_user(request.user, project_id)
        version_id = request.query_params.get("version_id")
        return Response(running_attributes(project, version_id=version_id))

"""Account-scoped draft workspace endpoints."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.models import TrainingJob
from apps.training.services import workspaces as service


def _workspace(user, job_id):
    return get_object_or_404(TrainingJob.objects.filter(owner=user), public_id=job_id)


def _entry(workspace, entry_id):
    return get_object_or_404(workspace.entries, public_id=entry_id)


def _serialize_entry(entry):
    return service.serialize_entries([entry])[0]


def _payload(request, *, required=False, max_bytes=service.MAX_DATA):
    upload = request.FILES.get("file")
    if upload:
        if upload.size > max_bytes:
            raise ValidationError({"file": "File exceeds the allowed size."})
        return upload.read(max_bytes + 1), True
    content = request.data.get("content")
    if content is not None:
        if not isinstance(content, str):
            raise ValidationError({"content": "Content must be text."})
        return content.encode("utf-8"), False
    if required:
        raise ValidationError({"file": "File content is required."})
    return None, False


class WorkspaceEntriesEndpoint(APIView):
    def post(self, request, job_id):
        workspace = _workspace(request.user, job_id)
        kind = request.data.get("kind", "")
        payload, uploaded = _payload(request, max_bytes=service.MAX_DATA if kind == "data" else service.MAX_TEXT)
        if kind == "data" and not uploaded:
            raise ValidationError({"file": "Upload a CSV file."})
        entry, revision = service.create_entry(workspace, revision=request.data.get("revision"),
            path=request.data.get("path"), kind=kind, payload=payload)
        return Response({"entry": _serialize_entry(entry), "revision": revision}, status=status.HTTP_201_CREATED)


class WorkspaceEntryEndpoint(APIView):
    def patch(self, request, job_id, entry_id):
        workspace = _workspace(request.user, job_id)
        entry = _entry(workspace, entry_id)
        kind = request.data.get("kind")
        payload, replacement = _payload(request, max_bytes=service.MAX_DATA if (kind or entry.kind) == "data" else service.MAX_TEXT)
        if (kind or entry.kind) == "data" and payload is not None and not replacement:
            raise ValidationError({"file": "Upload a CSV file."})
        path = request.data.get("path")
        entry, revision = service.edit_file(workspace, entry_id, revision=request.data.get("revision"),
            path=path, kind=kind, payload=payload, replacement=replacement)
        entry.refresh_from_db()
        return Response({"entry": _serialize_entry(entry), "revision": revision})

    def delete(self, request, job_id, entry_id):
        workspace = _workspace(request.user, job_id)
        _entry(workspace, entry_id)
        revision = service.delete_entry(workspace, entry_id, revision=request.data.get("revision"))
        return Response({"revision": revision})


class WorkspaceSecretEndpoint(APIView):
    def put(self, request, job_id, name):
        workspace = _workspace(request.user, job_id)
        secret, revision = service.set_secret(workspace, revision=request.data.get("revision"), name=name,
                                               value=request.data.get("value"))
        return Response({"name": secret.name, "updated_at": secret.updated_at.isoformat(), "revision": revision})

    def delete(self, request, job_id, name):
        workspace = _workspace(request.user, job_id)
        revision = service.delete_secret(workspace, revision=request.data.get("revision"), name=name)
        return Response({"revision": revision})

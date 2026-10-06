import {
  createDriftMonitoringJob,
  getDriftMonitor,
  getMonitorReferenceText,
  updateDriftMonitoringJob,
} from "@/features/monitoring/api/driftApi";
import { driftQueryKeys } from "@/features/monitoring/queryKeys";
import { useProductionData } from "@/features/monitoring/hooks/useDriftMonitoring";
import {
  useProjectOverview,
  useSnapshotText,
} from "@/features/overview/hooks/useProjectOverview";
import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export const THRESHOLD_VALUES = [500, 1000, 2000, 5000, 10000, 20000];
const MAX_REFERENCE_BYTES = 100 * 1024 * 1024;

export function useDriftMonitorForm(
  monitorId: string | undefined,
  requestedProjectId: string,
  onSaved: (projectId: string) => void,
) {
  const { t } = useTranslation("monitoring");
  const client = useQueryClient();
  const projects = useModelProjects();
  const existing = useQuery({
    queryKey: driftQueryKeys.configuration(monitorId ?? ""),
    queryFn: () => getDriftMonitor(monitorId!),
    enabled: Boolean(monitorId),
  });
  const projectId = existing.data?.project_id || requestedProjectId;
  const project = useProjectOverview(projectId);
  const endpoint = project.data?.active_endpoint;
  const versionId = monitorId
    ? existing.data?.version_id
    : endpoint?.version_id;
  const isRunning = Boolean(
    endpoint?.deployment_status === "succeeded" &&
    endpoint.version_id === versionId,
  );
  const [threshold, setThreshold] = useState<number | null>(null);
  const [upload, setUpload] = useState<{
    file: File;
    versionId: string;
    id: string;
  } | null>(null);
  const [fileError, setFileError] = useState("");
  const hasReference = Boolean(project.data?.reference_data);
  const reference =
    !monitorId && !hasReference && upload && upload.versionId === versionId
      ? upload.file
      : null;
  const currentReference = useSnapshotText(
    !monitorId ? project.data?.reference_data?.download_url : undefined,
    project.data?.reference_data
      ? `${versionId}:reference:${project.data.reference_data.checksum}`
      : undefined,
  );
  const monitorReference = useQuery({
    queryKey: driftQueryKeys.reference(monitorId ?? ""),
    queryFn: ({ signal }) => getMonitorReferenceText(monitorId!, signal),
    enabled: Boolean(monitorId && existing.data),
  });
  const localReference = useQuery({
    queryKey: driftQueryKeys.uploadPreview(upload?.id ?? ""),
    queryFn: async () => {
      if (!reference) return "";
      if (reference.name.toLowerCase().endsWith(".parquet")) {
        return "PARQUET_PREVIEW";
      }
      return await reference.text();
    },
    enabled: Boolean(reference),
  });
  const referenceQuery = monitorId
    ? monitorReference
    : hasReference
      ? currentReference
      : localReference;
  const production = useProductionData(
    projectId && versionId ? projectId : undefined,
    versionId,
  );
  const triggerThreshold =
    threshold ?? existing.data?.trigger_threshold ?? 1000;
  const allowedThresholds = [
    ...new Set([...THRESHOLD_VALUES, triggerThreshold]),
  ].sort((a, b) => a - b);
  const loading =
    project.isLoading ||
    projects.isLoading ||
    Boolean(monitorId && existing.isLoading);
  const error = project.error || projects.error || existing.error;
  const canSave =
    !loading &&
    !error &&
    !fileError &&
    Boolean(versionId) &&
    (Boolean(monitorId) ||
      (isRunning && (hasReference || Boolean(reference)))) &&
    Number.isInteger(triggerThreshold) &&
    triggerThreshold > 0;
  const save = useMutation({
    mutationFn: () => {
      if (!canSave) throw new Error(t("createPage.referenceRequired"));
      const payload = {
        project_id: projectId,
        version_id: versionId!,
        trigger_threshold: triggerThreshold,
        reference_file: reference,
      };
      return monitorId
        ? updateDriftMonitoringJob({ ...payload, id: monitorId })
        : createDriftMonitoringJob(payload);
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({
          queryKey: driftQueryKeys.monitors(projectId),
        }),
        client.invalidateQueries({
          queryKey: driftQueryKeys.configuration(monitorId ?? ""),
        }),
        client.invalidateQueries({
          queryKey: overviewQueryKeys.detail(projectId),
        }),
        client.invalidateQueries({
          queryKey: evolutionQueryKeys.snapshot(versionId!),
        }),
        client.invalidateQueries({
          queryKey: evolutionQueryKeys.versions(projectId),
        }),
        client.invalidateQueries({ queryKey: catalogQueryKeys.projects() }),
      ]);
      onSaved(projectId);
    },
  });
  return {
    projectId,
    versionId,
    projects,
    project,
    existing,
    production,
    triggerThreshold,
    allowedThresholds,
    reference,
    hasReference,
    referenceQuery,
    fileError,
    loading,
    error,
    canSave,
    save,
    dirty: threshold !== null || upload !== null,
    setThreshold,
    setReference: (file: File | null) => {
      setFileError("");
      setUpload(null);
      if (!file) return;
      const lower = file.name.toLowerCase();
      if (
        (!lower.endsWith(".csv") && !lower.endsWith(".parquet")) ||
        !file.size ||
        file.size > MAX_REFERENCE_BYTES
      ) {
        setFileError(t("createPage.invalidReference"));
        return;
      }
      if (isRunning && !hasReference && !monitorId)
        setUpload({ file, versionId: versionId!, id: crypto.randomUUID() });
    },
  };
}

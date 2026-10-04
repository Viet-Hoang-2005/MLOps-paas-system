import {
  createDriftMonitoringJob,
  getDriftMonitor,
  updateDriftMonitoringJob,
} from "@/features/monitoring/api/driftApi";
import {
  useProjectOverview,
  useRunningVersion,
} from "@/features/overview/hooks/useProjectOverview";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Input } from "@/shared/components/Input";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select } from "@/shared/components/Select";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

export default function CreateDriftMonitoringPage() {
  const { t } = useTranslation("monitoring");
  const { monitorId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const projects = useModelProjects();
  const existing = useQuery({
    queryKey: ["monitoring", "configuration", monitorId],
    queryFn: () => getDriftMonitor(monitorId!),
    enabled: Boolean(monitorId),
  });
  const projectId = existing.data?.project_id || params.get("projectId") || "";
  const project = useProjectOverview(projectId);
  const running = useRunningVersion(project.data?.active_endpoint?.version_id);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [reference, setReference] = useState<File | null>(null);
  const saved = useRef(false);
  const dirty = threshold !== null || reference !== null;
  const blocker = useBlocker(() => dirty && !saved.current);
  useEffect(() => {
    const handle = (event: BeforeUnloadEvent) => {
      if (dirty && !saved.current) event.preventDefault();
    };
    window.addEventListener("beforeunload", handle);
    return () => window.removeEventListener("beforeunload", handle);
  }, [dirty]);
  const hasReference = running.data?.artifacts.some(
    (asset) => asset.kind === "reference_data",
  );
  const save = useMutation({
    mutationFn: () => {
      const payload = {
        project_id: projectId,
        version_id: project.data!.active_endpoint!.version_id,
        trigger_threshold:
          threshold ?? existing.data?.trigger_threshold ?? 1000,
        reference_file: reference,
      };
      return monitorId
        ? updateDriftMonitoringJob({ ...payload, id: monitorId })
        : createDriftMonitoringJob(payload);
    },
    onSuccess: () => {
      saved.current = true;
      navigate(`/dashboard/projects/${projectId}/monitoring`);
    },
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title={t(monitorId ? "createPage.editTitle" : "createPage.createTitle")}
        back
      />
      <form
        className="space-y-6 rounded-surface border border-border bg-surface p-6"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Select
          value={projectId}
          disabled={Boolean(monitorId)}
          onChange={(value) => {
            setParams({ projectId: value });
            setReference(null);
          }}
          options={[
            { value: "", label: t("selectProject") },
            ...(projects.data?.models ?? [])
              .filter((item) => item.active_endpoint)
              .map((item) => ({ value: item.id, label: item.name })),
          ]}
        />
        <p className="text-color-muted-foreground">
          {t("referenceSnapshotHint")}
        </p>
        {monitorId ? (
          <p>{existing.data?.reference_name}</p>
        ) : hasReference ? (
          <p>{t("usingVersionReference")}</p>
        ) : (
          <FileDropzone
            accept=".csv"
            title={reference?.name || t("createPage.referenceData")}
            subtitle=".csv"
            onChange={setReference}
          />
        )}
        <Input
          type="number"
          min={1}
          label={t("trigger")}
          value={threshold ?? existing.data?.trigger_threshold ?? 1000}
          onChange={(event) => setThreshold(Number(event.target.value))}
        />
        {(save.isError || existing.isError || project.isError) && (
          <p role="alert" className="text-color-danger">
            {getApiErrorMessage(
              save.error || existing.error || project.error,
              t("createPage.saveFailed"),
            )}
          </p>
        )}
        <Button
          type="submit"
          loading={save.isPending}
          disabled={
            !project.data?.active_endpoint ||
            (!monitorId && !hasReference && !reference) ||
            (threshold !== null && threshold < 1)
          }
        >
          {t(monitorId ? "createPage.update" : "createPage.create")}
        </Button>
      </form>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title={t("unsaved")}
        description={t("leaveHint")}
        onConfirm={() => blocker.state === "blocked" && blocker.proceed()}
        onCancel={() => blocker.state === "blocked" && blocker.reset()}
      />
    </div>
  );
}

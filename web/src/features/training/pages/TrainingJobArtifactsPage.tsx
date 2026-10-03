import { Download, Rocket, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { Button } from "@/shared/components/Button";
import { PageBody } from "@/shared/components/PageBody";

export default function TrainingJobArtifactsPage() {
  const { t } = useTranslation("training");
  const navigate = useNavigate();
  const { job, downloadingOutput, downloadOutput, requestDeleteOutputs } =
    useTrainingJobDetailContext();
  const build = job.registration_build;
  const openBuild = () => {
    const query = new URLSearchParams({
      projectId: job.project_id,
      source: "training",
      jobId: job.id,
    });
    if (
      build &&
      ["pending", "queued", "building", "ready"].includes(build.status)
    )
      query.set("buildId", build.id);
    navigate(`/dashboard/deployments/new?${query}`);
  };
  return (
    <div className="space-y-6">
      <PageBody title={t("detail.artifactPage.title")}>
        <div className="space-y-4 p-6">
          <p>{t("workflow.snapshotHint")}</p>
          <dl className="space-y-3 break-all text-style-code-sm">
            <dt>{t("createFlow.source.sourceCode")}</dt>
            <dd>{job.code_snapshot_uri || "—"}</dd>
            <dt>{t("createFlow.source.referenceData")}</dt>
            <dd>{job.data_snapshot_uri || "—"}</dd>
            <dt>{t("createFlow.source.setReference")}</dt>
            <dd>
              {job.reference_path || "—"} · {job.reference_snapshot_uri || "—"}
            </dd>
            <dt>{t("detail.artifactPage.modelHeading")}</dt>
            <dd>{job.model_artifact_uri || "—"}</dd>
          </dl>
          <div className="flex flex-wrap gap-3">
            <Button
              icon={<Rocket className="h-4 w-4" />}
              disabled={job.status !== "completed" || !job.output_available}
              onClick={openBuild}
            >
              {t("workflow.openBuild")}
            </Button>
            <Button
              icon={<Download className="h-4 w-4" />}
              disabled={!job.output_available}
              loading={downloadingOutput}
              onClick={downloadOutput}
            >
              {t("detail.artifactPage.download")}
            </Button>
            <Button
              icon={<Trash2 className="h-4 w-4" />}
              variant="danger"
              disabled={!job.output_available}
              onClick={requestDeleteOutputs}
            >
              {t("detail.artifactPage.delete")}
            </Button>
          </div>
        </div>
      </PageBody>
    </div>
  );
}

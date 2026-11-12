import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { TrainingProjectAssignment } from "@/features/training/components/TrainingProjectAssignment";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";

export default function TrainingJobProjectPage() {
  const { job } = useTrainingJobDetailContext();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation("training");
  if (job.status !== "completed" || !job.output_available || job.deletion_pending) {
    return <p className="text-style-body text-color-muted-foreground">{t("studio.noOutput")}</p>;
  }
  return <TrainingProjectAssignment job={job}
    onBack={() => navigate(`/dashboard/training/jobs/${job.id}/artifacts`)}
    onSaved={(assigned) => {
      queryClient.setQueryData(trainingQueryKeys.job(assigned.id), assigned);
      void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.jobs() });
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      navigate(`/dashboard/training/jobs/${assigned.id}/artifacts`);
    }} />;
}

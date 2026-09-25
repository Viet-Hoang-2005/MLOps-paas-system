import { ArrowLeft, ArrowRight, Database, FileCode2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCreateTrainingJob } from "@/features/training/trainingFlowContext";
import type { ModelFlavor } from "@/features/catalog/types";
import { Button } from "@/shared/components/Button";
import { Picker } from "@/shared/components/Picker";
import { StepTitle } from "@/shared/components/StepTitle";

export default function SourceTrainingJobPage() {
  const { t } = useTranslation("training");
  const flow = useCreateTrainingJob();
  const transitioning = flow.transitionState !== "idle";
  return <><div className="space-y-8 rounded-surface border border-border bg-surface p-6"><StepTitle title={t("workflow.inputsTitle")} subtitle={t("workflow.inputsDescription")} /><div className="space-y-3"><p className="text-style-body-strong">{t("workflow.framework")}</p><Picker value={flow.sourceForm.model_flavor} onChange={(value) => flow.setSourceField("model_flavor", value as ModelFlavor)} options={[
    { value: "sklearn", title: t("table.flavors.sklearn"), description: "Scikit-learn" },
    { value: "xgboost", title: t("table.flavors.xgboost"), description: "XGBoost" },
    { value: "pytorch", title: t("table.flavors.pytorch"), description: "PyTorch" },
    { value: "tensorflow", title: t("table.flavors.tensorflow"), description: t("workflow.tensorflow") },
  ]} /></div><label className="block space-y-2 text-style-body-strong"><span className="flex items-center gap-2"><FileCode2 className="h-4 w-4" />{t("workflow.sourceZip")}</span><input className="block w-full rounded-surface border border-border bg-surface p-3" type="file" accept=".zip,application/zip" onChange={(event) => flow.setSourceField("source_zip", event.target.files?.[0] ?? null)} />{flow.sourceForm.source_zip && <small>{flow.sourceForm.source_zip.name}</small>}</label><label className="block space-y-2 text-style-body-strong"><span className="flex items-center gap-2"><Database className="h-4 w-4" />{t("workflow.dataset")}</span><input className="block w-full rounded-surface border border-border bg-surface p-3" type="file" accept=".csv,.parquet,.json,.jsonl,.zip,.gz" onChange={(event) => flow.setSourceField("training_data", event.target.files?.[0] ?? null)} />{flow.sourceForm.training_data && <small>{flow.sourceForm.training_data.name}</small>}</label><label className="block space-y-2 text-style-body-strong">{t("workflow.entryPoint")}<input className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={flow.sourceForm.entry_point} onChange={(event) => flow.setSourceField("entry_point", event.target.value)} placeholder="train.py" /></label><label className="block space-y-2 text-style-body-strong">{t("workflow.requirements")}<textarea className="block w-full rounded-surface border border-border bg-surface p-3 font-mono text-style-code-sm" rows={5} value={flow.sourceForm.requirements_text} onChange={(event) => flow.setSourceField("requirements_text", event.target.value)} placeholder="pandas==2.2.3" /></label></div><footer className="grid gap-3 pb-6 sm:grid-cols-2"><Button variant="secondary" icon={<ArrowLeft className="h-4 w-4" />} onClick={() => void flow.goToStep(1)}>{t("createFlow.actions.back")}</Button><Button disabled={transitioning || !flow.sourceForm.source_zip || !flow.sourceForm.training_data} onClick={() => void flow.continueFromSource()}>{t("createFlow.actions.continue")} <ArrowRight className="h-4 w-4" /></Button></footer></>;
}

import type {
  BuildInputForm,
  ModelArtifactFormat,
  ModelFlavor,
} from "@/features/projects/types";
import { useTranslation } from "react-i18next";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Picker } from "@/shared/components/Picker";
import { StepTitle } from "@/shared/components/StepTitle";
import { Switch } from "@/shared/components/Switch";
import { TextArea } from "@/shared/components/TextArea";

interface ModelArtifactFieldsProps {
  form: BuildInputForm;
  setField: <K extends keyof BuildInputForm>(
    field: K,
    value: BuildInputForm[K],
  ) => void;
  existingArtifactName?: string;
  existingAssets?: Record<string, string>;
  readOnly?: boolean;
}

const rawExtensions: Record<ModelFlavor, string[]> = {
  sklearn: [".pkl", ".joblib"],
  xgboost: [".xgb", ".pkl", ".joblib"],
  pytorch: [".pt", ".pth"],
  tensorflow: [".h5", ".keras"],
};

const packageExamples: Record<ModelFlavor, string[]> = {
  sklearn: [
    "model-package.zip",
    "├── MLmodel",
    "├── model.pkl",
    "├── requirements.txt",
    "└── python_env.yaml",
  ],
  xgboost: [
    "model-package.zip",
    "├── MLmodel",
    "├── model.xgb",
    "├── requirements.txt",
    "└── python_env.yaml",
  ],
  pytorch: [
    "model-package.zip",
    "├── MLmodel",
    "├── data/",
    "│   └── model.pth",
    "├── requirements.txt",
    "└── python_env.yaml",
  ],
  tensorflow: [
    "model-package.zip",
    "├── MLmodel",
    "├── data/",
    "│   └── model.keras",
    "├── requirements.txt",
    "└── python_env.yaml",
  ],
};

export function ModelArtifactFields({
  form,
  setField,
  existingArtifactName,
  existingAssets,
  readOnly = false,
}: ModelArtifactFieldsProps) {
  const { t } = useTranslation("deployments");
  const flavorOptions: Array<{
    value: ModelFlavor;
    title: string;
    description: string;
  }> = [
    {
      value: "sklearn",
      title: "Scikit-learn",
      description: t("uploadFlow.build.flavors.sklearn"),
    },
    {
      value: "xgboost",
      title: "XGBoost",
      description: t("uploadFlow.build.flavors.xgboost"),
    },
    {
      value: "pytorch",
      title: "PyTorch",
      description: t("uploadFlow.build.flavors.pytorch"),
    },
    {
      value: "tensorflow",
      title: "TensorFlow",
      description: t("uploadFlow.build.flavors.tensorflow"),
    },
  ];
  const extensions =
    form.artifact_format === "mlflow_zip"
      ? [".zip"]
      : rawExtensions[form.flavor];
  const selectFormat = (format: ModelArtifactFormat) => {
    if (format === form.artifact_format) return;
    setField("artifact_format", format);
    setField("source_artifact", null);
    if (format === "mlflow_zip") {
      setField("label_mapping_file", null);
      setField("metrics_file", null);
      setField("params_file", null);
      setField("model_insights_file", null);
      setField("feature_importance_file", null);
      setField("input_schema_file", null);
    }
  };

  const hasAdvancedAssets = Boolean(
    existingAssets &&
      (existingAssets.label_mapping ||
        existingAssets.input_schema ||
        existingAssets.metrics ||
        existingAssets.params ||
        existingAssets.model_insights ||
        existingAssets.feature_importance),
  );

  return (
    <div className="flex flex-col gap-8">
      <section className="space-y-5">
        <StepTitle
          title={t("uploadFlow.build.flavorTitle")}
          description={t("uploadFlow.build.flavorDescription")}
        />
        <Picker
          value={form.flavor}
          disabled={readOnly}
          onChange={(value) => setField("flavor", value)}
          options={flavorOptions}
        />
      </section>

      <hr className="border-border" />

      <section className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <StepTitle
            title={t("uploadFlow.build.artifactTitle")}
            description={t("uploadFlow.build.artifactDescription")}
          />
          <Switch
            value={form.artifact_format}
            disabled={readOnly}
            onChange={(value) => selectFormat(value as ModelArtifactFormat)}
            options={[
              { value: "raw", title: t("uploadFlow.build.raw") },
              { value: "mlflow_zip", title: t("uploadFlow.build.package") },
            ]}
            ariaLabel={t("uploadFlow.build.artifactFormat")}
          />
        </div>
        <FileDropzone
          accept={extensions.join(",")}
          disabled={readOnly}
          title={
            form.source_artifact?.name ||
            existingArtifactName ||
            (form.artifact_format === "mlflow_zip"
              ? t("uploadFlow.build.choosePackage")
              : t("uploadFlow.build.chooseRaw"))
          }
          subtitle={
            form.artifact_format === "mlflow_zip"
              ? t("uploadFlow.build.packageHint")
              : t("uploadFlow.build.allowedFiles", {
                  flavor: form.flavor,
                  extensions: extensions.join(", "),
                })
          }
          onChange={(file) => setField("source_artifact", file)}
        />
        {form.artifact_format === "mlflow_zip" ? (
          <div className="rounded-surface border border-border bg-muted p-4">
            <p className="text-style-body-strong text-color-foreground">
              {t("uploadFlow.build.packageLayout", { flavor: form.flavor })}
            </p>
            <p className="mt-1 text-style-caption text-color-muted-foreground">
              {t("uploadFlow.build.packageLayoutHint")}
            </p>
            <pre className="mt-4 overflow-x-auto rounded-compact border border-border bg-surface p-4 font-mono text-style-code-sm text-color-foreground">
              {packageExamples[form.flavor].join("\n")}
            </pre>
          </div>
        ) : (
          <details
            open={hasAdvancedAssets ? true : undefined}
            className="space-y-4 rounded-surface border border-border p-4"
          >
            <summary className="cursor-pointer text-style-body-strong">
              {t("advancedArtifacts")}
            </summary>
            <div className="grid gap-4 md:grid-cols-2">
              <FileDropzone
                accept=".pkl,.json"
                disabled={readOnly}
                title={
                  form.label_mapping_file?.name ||
                  existingAssets?.label_mapping ||
                  t("uploadFlow.build.attachments.labelMapping")
                }
                subtitle={t(
                  "uploadFlow.build.attachments.labelMappingSubtitle",
                )}
                hint={t("uploadFlow.build.attachments.labelMappingIndicators")}
                onChange={(file) => setField("label_mapping_file", file)}
              />
              <FileDropzone
                accept=".json"
                disabled={readOnly}
                title={
                  form.input_schema_file?.name ||
                  existingAssets?.input_schema ||
                  t("uploadFlow.build.attachments.inputSchema")
                }
                subtitle={t("uploadFlow.build.attachments.inputSchemaSubtitle")}
                hint={t("uploadFlow.build.attachments.inputSchemaIndicators")}
                onChange={(file) => setField("input_schema_file", file)}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <FileDropzone
                accept=".json"
                disabled={readOnly}
                title={
                  form.metrics_file?.name ||
                  existingAssets?.metrics ||
                  t("uploadFlow.build.attachments.metrics")
                }
                subtitle={t("uploadFlow.build.attachments.metricsSubtitle")}
                hint={t("uploadFlow.build.attachments.metricsIndicators")}
                onChange={(file) => setField("metrics_file", file)}
              />
              <FileDropzone
                accept=".json"
                disabled={readOnly}
                title={
                  form.params_file?.name ||
                  existingAssets?.params ||
                  t("uploadFlow.build.attachments.params")
                }
                subtitle={t("uploadFlow.build.attachments.paramsSubtitle")}
                hint={t("uploadFlow.build.attachments.paramsIndicators")}
                onChange={(file) => setField("params_file", file)}
              />
              <FileDropzone
                accept=".json"
                disabled={readOnly}
                title={
                  form.model_insights_file?.name ||
                  existingAssets?.model_insights ||
                  t("uploadFlow.build.attachments.insights")
                }
                subtitle={t("uploadFlow.build.attachments.insightsSubtitle")}
                hint={t("uploadFlow.build.attachments.insightsIndicators")}
                onChange={(file) => setField("model_insights_file", file)}
              />
              <FileDropzone
                accept=".json"
                disabled={readOnly}
                title={
                  form.feature_importance_file?.name ||
                  existingAssets?.feature_importance ||
                  t("uploadFlow.build.attachments.featureImportance")
                }
                subtitle={t(
                  "uploadFlow.build.attachments.featureImportanceSubtitle",
                )}
                hint={t(
                  "uploadFlow.build.attachments.featureImportanceIndicators",
                )}
                onChange={(file) => setField("feature_importance_file", file)}
              />
            </div>
          </details>
        )}
      </section>

      <hr className="border-border" />

      <section className="space-y-5">
        <StepTitle
          title={t("uploadFlow.build.requirementsTitle")}
          description={t("uploadFlow.build.requirementsDescription")}
        />
        <FileDropzone
          accept=".txt,text/plain"
          disabled={readOnly}
          title={
            form.requirements_file?.name ||
            t("uploadFlow.build.requirementsFile")
          }
          subtitle={t("uploadFlow.build.optional")}
          onChange={(file) => {
            setField("requirements_file", file);
            if (file)
              void file
                .text()
                .then((content) => setField("requirements_text", content));
          }}
        />
        <TextArea
          id="build-requirements"
          readOnly={readOnly}
          value={form.requirements_text}
          onChange={(value) => setField("requirements_text", value)}
          placeholder={"scikit-learn==1.7.2\npandas==2.2.1\nnumpy==1.26.4"}
          minHeight="min-h-48"
        />
      </section>
    </div>
  );
}

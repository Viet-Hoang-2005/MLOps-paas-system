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
import { toast } from "@/shared/types/toastStore";

interface ModelArtifactFieldsProps {
  form: BuildInputForm;
  setField: <K extends keyof BuildInputForm>(
    field: K,
    value: BuildInputForm[K],
  ) => void;
  existingArtifactName?: string;
  existingAssets?: Record<string, string>;
  onRemoveArtifact?: () => void;
  onRemoveAsset?: (kind: string) => void;
  readOnly?: boolean;
}

const rawExtensions: Record<ModelFlavor, string[]> = {
  sklearn: [".pkl", ".joblib"],
  xgboost: [".xgb", ".pkl", ".joblib"],
  pytorch: [".pt", ".pth"],
  tensorflow: [".h5", ".keras"],
};

const MAX_SOURCE_ARTIFACT_BYTES: Record<
  ModelFlavor,
  Record<ModelArtifactFormat, number>
> = {
  sklearn: {
    raw: 200 * 1024 * 1024,
    mlflow_zip: 500 * 1024 * 1024,
  },
  xgboost: {
    raw: 200 * 1024 * 1024,
    mlflow_zip: 500 * 1024 * 1024,
  },
  pytorch: {
    raw: 1024 * 1024 * 1024,
    mlflow_zip: 1024 * 1024 * 1024,
  },
  tensorflow: {
    raw: 1024 * 1024 * 1024,
    mlflow_zip: 1024 * 1024 * 1024,
  },
};

const MAX_SOURCE_ARTIFACT_LABELS: Record<
  ModelFlavor,
  Record<ModelArtifactFormat, string>
> = {
  sklearn: {
    raw: "200 MB",
    mlflow_zip: "500 MB",
  },
  xgboost: {
    raw: "200 MB",
    mlflow_zip: "500 MB",
  },
  pytorch: {
    raw: "1 GB",
    mlflow_zip: "1 GB",
  },
  tensorflow: {
    raw: "1 GB",
    mlflow_zip: "1 GB",
  },
};

const MAX_JSON_ATTRIBUTE_BYTES = 10 * 1024 * 1024;

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
  onRemoveArtifact,
  onRemoveAsset,
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

  const maxSizeBytes =
    MAX_SOURCE_ARTIFACT_BYTES[form.flavor][form.artifact_format];
  const maxSizeLabel =
    MAX_SOURCE_ARTIFACT_LABELS[form.flavor][form.artifact_format];

  const handleJsonFileChange = (
    file: File | null,
    field:
      | "label_mapping_file"
      | "input_schema_file"
      | "metrics_file"
      | "params_file"
      | "model_insights_file"
      | "feature_importance_file",
  ) => {
    if (file) {
      if (!file.name.toLowerCase().endsWith(".json")) {
        toast.error(t("uploadFlow.build.jsonFormatError"));
        return;
      }
      if (file.size > MAX_JSON_ATTRIBUTE_BYTES) {
        toast.error(t("uploadFlow.build.jsonTooLarge", { max: "10 MB" }));
        return;
      }
    }
    setField(field, file);
  };

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
          onChange={(value) => {
            setField("flavor", value);
            if (form.source_artifact) {
              const newMax =
                MAX_SOURCE_ARTIFACT_BYTES[value as ModelFlavor][
                  form.artifact_format
                ];
              if (form.source_artifact.size > newMax) {
                setField("source_artifact", null);
                toast.warning(
                  t("uploadFlow.build.artifactRemovedExceedsLimit", {
                    max: MAX_SOURCE_ARTIFACT_LABELS[value as ModelFlavor][
                      form.artifact_format
                    ],
                  }),
                );
              }
            }
          }}
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
              ? t("uploadFlow.build.packageHint", { maxSize: maxSizeLabel })
              : t("uploadFlow.build.allowedFiles", {
                  flavor: form.flavor,
                  extensions: extensions.join(", "),
                  maxSize: maxSizeLabel,
                })
          }
          hasFile={Boolean(form.source_artifact || existingArtifactName)}
          onRemove={() => {
            if (onRemoveArtifact) {
              onRemoveArtifact();
            } else {
              setField("source_artifact", null);
            }
          }}
          onChange={(file) => {
            if (file) {
              const ext = "." + file.name.split(".").pop()?.toLowerCase();
              if (!extensions.includes(ext)) {
                toast.error(
                  form.artifact_format === "mlflow_zip"
                    ? t("uploadFlow.build.packageLayoutHint")
                    : t("uploadFlow.build.allowedFiles", {
                        flavor: form.flavor,
                        extensions: extensions.join(", "),
                        maxSize: maxSizeLabel,
                      }),
                );
                return;
              }
              if (file.size > maxSizeBytes) {
                toast.error(
                  t("uploadFlow.build.artifactTooLarge", {
                    max: maxSizeLabel,
                  }),
                );
                return;
              }
            }
            setField("source_artifact", file);
          }}
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
                accept=".json"
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
                hasFile={Boolean(
                  form.label_mapping_file || existingAssets?.label_mapping,
                )}
                onRemove={() => {
                  onRemoveAsset?.("label_mapping");
                  setField("label_mapping_file", null);
                }}
                onChange={(file) =>
                  handleJsonFileChange(file, "label_mapping_file")
                }
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
                hasFile={Boolean(
                  form.input_schema_file || existingAssets?.input_schema,
                )}
                onRemove={() => {
                  onRemoveAsset?.("input_schema");
                  setField("input_schema_file", null);
                }}
                onChange={(file) =>
                  handleJsonFileChange(file, "input_schema_file")
                }
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
                hasFile={Boolean(
                  form.metrics_file || existingAssets?.metrics,
                )}
                onRemove={() => {
                  onRemoveAsset?.("metrics");
                  setField("metrics_file", null);
                }}
                onChange={(file) =>
                  handleJsonFileChange(file, "metrics_file")
                }
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
                hasFile={Boolean(
                  form.params_file || existingAssets?.params,
                )}
                onRemove={() => {
                  onRemoveAsset?.("params");
                  setField("params_file", null);
                }}
                onChange={(file) =>
                  handleJsonFileChange(file, "params_file")
                }
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
                hasFile={Boolean(
                  form.model_insights_file || existingAssets?.model_insights,
                )}
                onRemove={() => {
                  onRemoveAsset?.("model_insights");
                  setField("model_insights_file", null);
                }}
                onChange={(file) =>
                  handleJsonFileChange(file, "model_insights_file")
                }
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
                hasFile={Boolean(
                  form.feature_importance_file || existingAssets?.feature_importance,
                )}
                onRemove={() => {
                  onRemoveAsset?.("feature_importance");
                  setField("feature_importance_file", null);
                }}
                onChange={(file) =>
                  handleJsonFileChange(file, "feature_importance_file")
                }
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
          hasFile={Boolean(form.requirements_file)}
          onRemove={() => {
            setField("requirements_file", null);
            setField("requirements_text", "");
          }}
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

import { ArrowLeft, ArrowRight, Database, FileCode2 } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import {
  SourceEditor,
  type SourceEditorHandle,
} from "@/features/catalog/components/SourceEditor";
import { useCreateTrainingJob } from "@/features/training/trainingFlowContext";
import type { ModelFlavor } from "@/features/catalog/types";
import { Button } from "@/shared/components/Button";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Picker } from "@/shared/components/Picker";
import { StepTitle } from "@/shared/components/StepTitle";
import { TextArea } from "@/shared/components/TextArea";

export default function SourceTrainingJobPage() {
  const { t } = useTranslation("training");
  const flow = useCreateTrainingJob();
  const codeEditor = useRef<SourceEditorHandle>(null);
  const dataEditor = useRef<SourceEditorHandle>(null);
  const transitioning = flow.transitionState !== "idle";

  if (!flow.project) return null;

  return (
    <>
      <div className="space-y-8 rounded-surface border border-border bg-surface p-6">
        <StepTitle
          title={t("createFlow.source.title")}
          subtitle={t("createFlow.source.description")}
        />
        <div className="space-y-3">
          <p className="text-style-body-strong text-color-foreground">
            {t("createFlow.source.flavor")}
          </p>
          <Picker
            value={flow.sourceForm.model_flavor}
            onChange={(value) =>
              flow.setSourceField("model_flavor", value as ModelFlavor)
            }
            options={[
              {
                value: "sklearn",
                title: t("table.flavors.sklearn"),
                description: t("createFlow.source.flavors.sklearn"),
              },
              {
                value: "xgboost",
                title: t("table.flavors.xgboost"),
                description: t("createFlow.source.flavors.xgboost"),
              },
              {
                value: "pytorch",
                title: t("table.flavors.pytorch"),
                description: t("createFlow.source.flavors.pytorch"),
              },
              {
                value: "tensorflow",
                title: t("table.flavors.tensorflow"),
                description: t("createFlow.source.flavors.tensorflow"),
              },
            ]}
          />
        </div>

        <SourceEditor
          ref={codeEditor}
          modelId={flow.project.id}
          fileType="code_file"
          title={t("createFlow.source.sourceCode")}
          icon={<FileCode2 className="h-4 w-4" />}
          accept=".zip,.py,.json,.yaml,.yml"
          editorType="code"
          currentEntryPoint={flow.sourceForm.entry_point}
          onSetEntryPoint={(file) => flow.setSourceField("entry_point", file)}
          onDirtyChange={(dirty) => flow.setEditorDirty("code", dirty)}
        />
        <SourceEditor
          ref={dataEditor}
          modelId={flow.project.id}
          fileType="data_file"
          title={t("createFlow.source.referenceData")}
          icon={<Database className="h-4 w-4" />}
          accept=".zip,.csv,.parquet"
          editorType="csv"
          onDirtyChange={(dirty) => flow.setEditorDirty("data", dirty)}
        />
        <div className="space-y-4">
          <p className="text-style-body-strong text-color-foreground">
            {t("createFlow.source.requirements")}
          </p>
          <FileDropzone
            accept=".txt,text/plain"
            title={
              flow.sourceForm.requirements_file?.name ||
              t("createFlow.source.requirementsFile", {
                defaultValue: "Upload requirements.txt",
              })
            }
            subtitle={t("createFlow.source.optional", {
              defaultValue: "Optional",
            })}
            onChange={(file) => {
              flow.setSourceField("requirements_file", file);
              if (file)
                void file
                  .text()
                  .then((content) =>
                    flow.setSourceField("requirements_text", content),
                  );
            }}
          />
          <TextArea
            minHeight="min-h-40"
            value={flow.sourceForm.requirements_text}
            placeholder="pandas==2.2.3"
            onChange={(value) =>
              flow.setSourceField("requirements_text", value)
            }
          />
        </div>
      </div>

      <footer className="grid gap-3 pb-6 sm:grid-cols-2">
        <Button
          variant="secondary"
          icon={<ArrowLeft className="h-4 w-4" />}
          onClick={() => void flow.goToStep(1)}
        >
          {t("createFlow.actions.back")}
        </Button>
        <Button
          loading={flow.transitionState === "saving-source"}
          disabled={transitioning}
          onClick={() =>
            void flow.continueFromSource([
              async () => codeEditor.current?.save() ?? true,
              async () => dataEditor.current?.save() ?? true,
            ])
          }
        >
          {t("createFlow.actions.continue")} <ArrowRight className="h-4 w-4" />
        </Button>
      </footer>
    </>
  );
}

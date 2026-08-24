import { ArrowLeft, ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ProjectMetadataFields } from "@/features/deploy/components/ProjectMetadataFields";
import { useUploadModel } from "@/features/deploy/uploadModelContext";
import { Button } from "@/shared/components/Button";

export default function MetadataModelPage() {
  const { t } = useTranslation("deploy");
  const {
    project,
    metadataForm,
    transitionState,
    setMetadataField,
    continueFromMetadata,
    requestExit,
  } = useUploadModel();

  return (
    <>
      <div className="rounded-surface border border-border bg-surface p-6 lg:p-8">
        <ProjectMetadataFields
          form={metadataForm}
          project={project}
          setField={setMetadataField}
        />
      </div>
      <footer className="grid gap-3 pb-6 sm:grid-cols-2">
        <Button
          variant="secondary"
          size="md"
          icon={<ArrowLeft className="h-4 w-4" />}
          disabled={transitionState !== "idle"}
          onClick={requestExit}
        >
          {t("uploadFlow.actions.back")}
        </Button>
        <Button
          size="md"
          loading={transitionState === "saving-metadata"}
          disabled={transitionState !== "idle"}
          onClick={() => void continueFromMetadata()}
        >
          {t("uploadFlow.actions.continue")} <ArrowRight className="h-4 w-4" />
        </Button>
      </footer>
    </>
  );
}

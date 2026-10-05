import { getApiErrorMessage } from "@/shared/api/errors";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { Picker } from "@/shared/components/Picker";
import { TextArea } from "@/shared/components/TextArea";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export interface EditMetadataDialogProps {
  open: boolean;
  onClose: () => void;
  project: {
    name: string;
    description: string;
    access_mode: "private" | "public";
  };
  onSave: (payload: {
    name: string;
    description: string;
    access_mode: "private" | "public";
  }) => Promise<unknown> | void;
  loading?: boolean;
  error?: unknown;
}

interface EditMetadataDialogContentProps {
  onClose: () => void;
  project: EditMetadataDialogProps["project"];
  onSave: EditMetadataDialogProps["onSave"];
  loading?: boolean;
  error?: unknown;
}

function EditMetadataDialogContent({
  onClose,
  project,
  onSave,
  loading = false,
  error,
}: EditMetadataDialogContentProps) {
  const { t } = useTranslation("projects");
  const { t: tCommon } = useTranslation("common");

  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  const [accessMode, setAccessMode] = useState<"private" | "public">(
    project.access_mode,
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSave({
      name: name.trim(),
      description: description.trim(),
      access_mode: accessMode,
    });
  };

  return (
    <BaseDialog title={t("workflow.editMetadata")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error ? (
          <p role="alert" className="text-color-danger text-style-body">
            {getApiErrorMessage(error, t("workflow.failed"))}
          </p>
        ) : null}
        <Input
          id="project-name"
          label={t("workflow.name")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={loading}
          required
        />
        <TextArea
          id="project-description"
          label={t("workflow.description")}
          value={description}
          onChange={setDescription}
          disabled={loading}
        />
        <Picker
          title={t("workflow.accessMode")}
          value={accessMode}
          onChange={(val) => setAccessMode(val as "private" | "public")}
          options={[
            {
              value: "private",
              title: t("workflow.privateTitle"),
              description: t("workflow.privateDescription"),
            },
            {
              value: "public",
              title: t("workflow.publicTitle"),
              description: t("workflow.publicDescription"),
            },
          ]}
        />
        <div className="mt-6 flex justify-end gap-3 pt-2">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={loading}
          >
            {tCommon("actions.cancel")}
          </Button>
          <Button
            type="submit"
            loading={loading}
            disabled={!name.trim() || loading}
          >
            {tCommon("actions.save")}
          </Button>
        </div>
      </form>
    </BaseDialog>
  );
}

export function EditMetadataDialog({
  open,
  onClose,
  project,
  onSave,
  loading,
  error,
}: EditMetadataDialogProps) {
  if (!open) return null;

  return (
    <EditMetadataDialogContent
      onClose={onClose}
      project={project}
      onSave={onSave}
      loading={loading}
      error={error}
    />
  );
}

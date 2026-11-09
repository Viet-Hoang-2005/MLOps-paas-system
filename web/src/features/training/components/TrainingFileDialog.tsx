import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Input } from "@/shared/components/Input";

export type TrainingFileKind = "script" | "data" | "config" | "document" | "requirements";
export interface TrainingFileSelection { path: string; kind: TrainingFileKind; file: File | null }
export interface TrainingFileDialogProps {
  existing?: { path: string; kind: TrainingFileKind };
  parentPath?: string;
  hasRequirements: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (selection: TrainingFileSelection) => void;
}

const extensions: Record<TrainingFileKind, string> = {
  script: ".py", data: ".csv", config: ".json", document: ".md", requirements: ".txt",
};

export function TrainingFileDialog({ existing, parentPath = "", hasRequirements, saving = false, onClose, onSave }: TrainingFileDialogProps) {
  const { t } = useTranslation("training");
  const [kind, setKind] = useState<TrainingFileKind>(existing?.kind ?? "script");
  const [name, setName] = useState(existing?.path.split("/").pop() ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const lockedRequirements = existing?.kind === "requirements";
  const isRequirements = kind === "requirements";
  const kinds = [
    { value: "script", label: t("workspace.fileDialog.script") },
    { value: "data", label: t("workspace.fileDialog.data") },
    { value: "config", label: t("workspace.fileDialog.config") },
    { value: "document", label: t("workspace.fileDialog.document") },
    { value: "requirements", label: t("workspace.fileDialog.requirements") },
  ] as const;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const filename = isRequirements ? "requirements.txt" : name.trim();
    if (!filename || filename === "." || filename === ".." || /[\\/]/.test(filename)
      || Array.from(filename).some((character) => character.charCodeAt(0) < 32)
      || !filename.toLowerCase().endsWith(extensions[kind]) || (!isRequirements && filename.toLowerCase() === "requirements.txt")) {
      setError(t("workspace.fileDialog.invalidName"));
      return;
    }
    if (!existing && kind === "data" && !file) {
      setError(t("workspace.fileDialog.csvRequired"));
      return;
    }
    if (!existing && isRequirements && hasRequirements) {
      setError(t("workspace.fileDialog.requirementsExists"));
      return;
    }
    const parent = existing?.path.includes("/") ? existing.path.slice(0, existing.path.lastIndexOf("/")) : parentPath;
    onSave({ kind, path: isRequirements ? filename : (parent ? `${parent}/${filename}` : filename), file });
  };

  return (
    <BaseDialog title={existing ? t("workspace.fileDialog.edit") : t("workspace.fileDialog.create")} onClose={onClose} description={t("workspace.fileDialog.description")}>
      <form onSubmit={submit} className="space-y-4">
        <label className="block space-y-2 text-style-body-strong text-color-foreground">
          <span>{t("workspace.fileDialog.type")}</span>
          <select aria-label={t("workspace.fileDialog.type")} value={kind} disabled={Boolean(lockedRequirements) || saving}
            onChange={(event) => { setKind(event.target.value as TrainingFileKind); setFile(null); setError(""); }}
            className="h-14 w-full rounded-control border border-input bg-surface px-4 text-style-body text-color-foreground">
            {kinds.map((item) => <option key={item.value} value={item.value}
              disabled={item.value === "requirements" && !lockedRequirements && (hasRequirements || Boolean(existing))}>{item.label}</option>)}
          </select>
        </label>
        <Input label={t("workspace.fileDialog.name")} value={isRequirements ? "requirements.txt" : name}
          disabled={isRequirements || saving} onChange={(event) => { setName(event.target.value); setError(""); }} error={error || undefined} />
        {!lockedRequirements && <FileDropzone accept={extensions[kind]} title={file?.name ?? t("workspace.fileDialog.upload")}
          subtitle={kind === "data" && !existing ? t("workspace.fileDialog.required") : t("workspace.fileDialog.optional")}
          hasFile={Boolean(file)} onChange={(next) => { setFile(next); setError(""); }} disabled={saving} removeTitle={t("workspace.fileDialog.removeUpload")} />}
        {lockedRequirements && <p className="text-style-caption text-color-muted-foreground">{t("workspace.fileDialog.requirementsEdit")}</p>}
        {hasRequirements && !existing && <p className="text-style-caption text-color-muted-foreground">{t("workspace.fileDialog.requirementsExists")}</p>}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>{t("workspace.fileDialog.cancel")}</Button>
          <Button type="submit" loading={saving}>{existing ? t("workspace.fileDialog.save") : t("workspace.fileDialog.createAction")}</Button>
        </div>
      </form>
    </BaseDialog>
  );
}

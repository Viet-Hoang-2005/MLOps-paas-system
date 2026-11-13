import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Input } from "@/shared/components/Input";
import { Select, type SelectOption } from "@/shared/components/Select";

export type InputFileKind =
  "script" | "data" | "config" | "document" | "requirements";
export interface InputFileSelection {
  path: string;
  kind: InputFileKind;
  file: File | null;
}
export interface InputFileDialogProps {
  existing?: { path: string; kind: InputFileKind };
  parentPath?: string;
  hasRequirements: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (selection: InputFileSelection) => void;
}

const extensions: Record<InputFileKind, string> = {
  script: ".py",
  data: ".csv",
  config: ".json",
  document: ".md",
  requirements: ".txt",
};

export function InputFileDialog({
  existing,
  parentPath = "",
  hasRequirements,
  saving = false,
  onClose,
  onSave,
}: InputFileDialogProps) {
  const { t } = useTranslation("training");
  const [kind, setKind] = useState<InputFileKind>(existing?.kind ?? "script");
  const [name, setName] = useState(existing?.path.split("/").pop() ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const lockedRequirements = existing?.kind === "requirements";
  const isRequirements = kind === "requirements";
  const kinds: SelectOption[] = [
    { value: "script", label: t("workspace.fileDialog.script") },
    { value: "data", label: t("workspace.fileDialog.data") },
    { value: "config", label: t("workspace.fileDialog.config") },
    { value: "document", label: t("workspace.fileDialog.document") },
    {
      value: "requirements",
      label: t("workspace.fileDialog.requirements"),
      disabled: !lockedRequirements && (hasRequirements || Boolean(existing)),
    },
  ];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    let filename: string;

    if (isRequirements) {
      filename = "requirements.txt";
    } else {
      const raw = name.trim();
      const expectedExt = extensions[kind];

      if (
        !raw ||
        raw === "." ||
        raw === ".." ||
        /[\\/]/.test(raw) ||
        Array.from(raw).some((character) => character.charCodeAt(0) < 32)
      ) {
        setError(t("workspace.fileDialog.invalidName"));
        return;
      }

      const lastDot = raw.lastIndexOf(".");
      if (lastDot === -1) {
        // Tự map đuôi file theo loại file đã chọn trong Select khi người dùng không nhập đuôi
        filename = `${raw}${expectedExt}`;
      } else {
        // Người dùng có nhập đuôi file (hoặc có dấu chấm)
        if (lastDot === 0 || lastDot === raw.length - 1) {
          setError(t("workspace.fileDialog.invalidName"));
          return;
        }

        const userExt = raw.slice(lastDot).toLowerCase();
        // Đảm bảo đuôi file phải khớp với loại file đã chọn trong Select
        if (userExt !== expectedExt) {
          setError(t("workspace.fileDialog.invalidName"));
          return;
        }

        filename = raw;
      }

      if (filename.toLowerCase() === "requirements.txt") {
        setError(t("workspace.fileDialog.invalidName"));
        return;
      }
    }

    if (!existing && kind === "data" && !file) {
      setError(t("workspace.fileDialog.csvRequired"));
      return;
    }
    if (!existing && isRequirements && hasRequirements) {
      setError(t("workspace.fileDialog.requirementsExists"));
      return;
    }
    const parent = existing?.path.includes("/")
      ? existing.path.slice(0, existing.path.lastIndexOf("/"))
      : parentPath;
    onSave({
      kind,
      path: isRequirements
        ? filename
        : parent
          ? `${parent}/${filename}`
          : filename,
      file,
    });
  };

  return (
    <BaseDialog
      title={
        existing
          ? t("workspace.fileDialog.edit")
          : t("workspace.fileDialog.create")
      }
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-4">
        <Select
          label={t("workspace.fileDialog.type")}
          value={kind}
          disabled={Boolean(lockedRequirements) || saving}
          onChange={(val) => {
            setKind(val as InputFileKind);
            setFile(null);
            setError("");
          }}
          options={kinds}
        />
        <Input
          label={t("workspace.fileDialog.name")}
          value={isRequirements ? "requirements.txt" : name}
          disabled={isRequirements || saving}
          onChange={(event) => {
            setName(event.target.value);
            setError("");
          }}
          error={error || undefined}
        />
        {!lockedRequirements && (
          <FileDropzone
            accept={extensions[kind]}
            title={file?.name ?? t("workspace.fileDialog.upload")}
            subtitle={
              kind === "data" && !existing
                ? t("workspace.fileDialog.required")
                : t("workspace.fileDialog.optional")
            }
            hasFile={Boolean(file)}
            onChange={(next) => {
              setFile(next);
              setError("");
            }}
            disabled={saving}
            removeTitle={t("workspace.fileDialog.removeUpload")}
          />
        )}
        {lockedRequirements && (
          <p className="text-style-caption text-color-muted-foreground">
            {t("workspace.fileDialog.requirementsEdit")}
          </p>
        )}
        {hasRequirements && !existing && (
          <p className="text-style-caption text-color-muted-foreground">
            {t("workspace.fileDialog.requirementsExists")}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={saving}
          >
            {t("workspace.fileDialog.cancel")}
          </Button>
          <Button type="submit" loading={saving}>
            {existing
              ? t("workspace.fileDialog.save")
              : t("workspace.fileDialog.createAction")}
          </Button>
        </div>
      </form>
    </BaseDialog>
  );
}

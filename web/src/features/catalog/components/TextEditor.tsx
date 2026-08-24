import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { LazyCodeEditor } from "@/shared/components/LazyCodeEditor";
import { Trash2, RotateCcw, Upload, Save, FileArchive } from "lucide-react";
import { toast } from "@/shared/components/toastStore";
import type { ModelProject } from "@/features/catalog/types";

export interface TextEditorProps {
  modelProject: ModelProject;
  onDirtyChange?: (isDirty: boolean) => void;
  onContentChange?: (content: string) => void;
  /** Called after the current training-job requirements are accepted locally. */
  onSaveSuccess?: () => void;
}

export function TextEditor({
  modelProject,
  onDirtyChange,
  onContentChange,
  onSaveSuccess,
}: TextEditorProps) {
  const { t } = useTranslation("catalog");
  const [content, setContent] = useState<string>("");
  const [originalContent, setOriginalContent] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isDirty = content !== originalContent;

  // Notify parent when dirty state changes
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  // Notify parent of current content on every change (real-time)
  useEffect(() => {
    onContentChange?.(content);
  }, [content, onContentChange]);

  // Reset editor when a different model is selected
  const [prevModelId, setPrevModelId] = useState(modelProject.id);
  if (prevModelId !== modelProject.id) {
    setPrevModelId(modelProject.id);
    setContent("");
    setOriginalContent("");
  }

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        setContent(text);
      } catch {
        toast.error(t("requirementsEditor.readFailed"));
      }
      e.target.value = "";
    },
    [t],
  );

  const handleDelete = useCallback(() => {
    setContent("");
  }, []);

  const handleReset = useCallback(() => {
    setContent(originalContent);
  }, [originalContent]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      setOriginalContent(content);
      onSaveSuccess?.();
      toast.success(t("requirementsEditor.attached"));
    } catch {
      toast.error(t("requirementsEditor.attachFailed"));
    } finally {
      setSaving(false);
    }
  }, [content, onSaveSuccess, t]);

  const isEmpty = content.trim() === "";

  return (
    <div className="flex flex-col h-96 border border-border rounded-surface overflow-hidden bg-surface shadow-sm">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-border bg-muted px-3 py-2">
        <div className="text-style-body-strong text-color-foreground flex items-center gap-2">
          <FileArchive className="w-4 h-4" />
          requirements.txt
          {isDirty && (
            <span
              className="ml-1 inline-block h-2 w-2 rounded-full bg-warning"
              title={t("requirementsEditor.unsaved")}
            />
          )}
        </div>
        <div className="flex items-center gap-1">
          <input
            type="file"
            className="hidden"
            accept=".txt"
            ref={fileInputRef}
            onChange={handleUpload}
          />
          <button
            className="p-2 rounded-full hover:bg-muted transition-colors"
            onClick={handleDelete}
            title={t("requirementsEditor.clear")}
          >
            <Trash2 className="w-4 h-4 text-color-danger" />
          </button>
          <button
            className="p-2 rounded-full hover:bg-muted transition-colors disabled:opacity-40"
            onClick={handleReset}
            disabled={!isDirty}
            title={t("requirementsEditor.reset")}
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <button
            className="p-2 rounded-full hover:bg-muted transition-colors"
            onClick={() => fileInputRef.current?.click()}
            title={t("requirementsEditor.upload")}
          >
            <Upload className="w-4 h-4" />
          </button>
          <button
            className="p-2 rounded-full hover:bg-muted transition-colors disabled:opacity-40"
            onClick={handleSave}
            disabled={saving || !isDirty}
            title={t("requirementsEditor.useForTraining")}
          >
            {saving ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
            ) : (
              <Save className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {isEmpty ? (
          <button
            onClick={() => fileInputRef.current?.click()}
            className="w-full h-full flex flex-col items-center justify-center border-0 bg-surface hover:bg-muted transition-colors group cursor-pointer"
          >
            <Upload className="w-10 h-10 mb-3 text-color-muted-foreground group-hover:text-color-info transition-colors" />
            <p className="text-color-muted-foreground font-medium group-hover:text-color-primary transition-colors">
              {t("requirementsEditor.uploadPrompt")}
            </p>
            <p className="text-style-body text-color-muted-foreground mt-1">
              {t("requirementsEditor.typingHint")}
            </p>
            <p className="text-style-caption text-color-muted-foreground mt-3">
              {t("requirementsEditor.accepted")}
            </p>
          </button>
        ) : (
          <LazyCodeEditor
            height="100%"
            language="plaintext"
            theme="light"
            value={content}
            onChange={(val) => setContent(val ?? "")}
            options={{
              minimap: { enabled: false },
              // typography-ignore: Monaco requires a numeric pixel value.
              fontSize: 14,
              wordWrap: "on",
              scrollBeyondLastLine: false,
              lineNumbers: "on",
              occurrencesHighlight: "off",
              selectionHighlight: false,
            }}
          />
        )}
      </div>
    </div>
  );
}

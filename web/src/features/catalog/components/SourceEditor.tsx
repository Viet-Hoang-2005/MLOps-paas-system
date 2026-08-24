import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/app/theme/useTheme";
import { LazyCodeEditor } from "@/shared/components/LazyCodeEditor";
import {
  Save,
  FolderOpen,
  Upload,
  Play,
  FilePlus,
  FolderPlus,
  Trash2,
} from "lucide-react";
import { CSVEditor } from "@/shared/components/CSVEditor";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import {
  listSourceCodeFiles,
  uploadSourceCodeFile,
  deleteSourceCodeFile,
  listReferenceFiles,
  uploadReferenceFile,
  deleteReferenceFile,
  type WorkspaceFile as S3File,
} from "@/features/catalog/api/catalogApi";
import { SourceTree } from "./SourceTree";
import { buildSourceTree, type CreatingFileState } from "./sourceTreeModel";

export interface SourceEditorProps {
  modelId: string;
  fileType: "code_file" | "data_file";
  title: string;
  icon: React.ReactNode;
  accept: string;
  editorType: "code" | "csv";
  onDirtyChange?: (isDirty: boolean) => void;
  onSetEntryPoint?: (filename: string) => void;
  currentEntryPoint?: string;
  setAsMainLabel?: string;
  entryPointExtension?: string;
}

export interface SourceEditorHandle {
  save: () => Promise<boolean>;
}

export const SourceEditor = forwardRef<SourceEditorHandle, SourceEditorProps>(
  function SourceEditor(
    {
      modelId,
      fileType,
      title,
      icon,
      accept,
      editorType,
      onDirtyChange,
      onSetEntryPoint,
      currentEntryPoint,
      setAsMainLabel,
      entryPointExtension = ".py",
    },
    ref,
  ) {
    const { t } = useTranslation("catalog");
    const { resolvedTheme } = useTheme();
    const [files, setFiles] = useState<S3File[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    const [unsavedContents, setUnsavedContents] = useState<
      Record<string, string>
    >({});
    const isDirty = Object.keys(unsavedContents).length > 0;

    const [selectedPath, setSelectedPath] = useState<string | null>(null);
    const [fileContent, setFileContent] = useState<string>("");
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
      new Set(),
    );
    const [creatingFile, setCreatingFile] = useState<CreatingFileState | null>(
      null,
    );
    const [deleteConfirmPath, setDeleteConfirmPath] = useState<string | null>(
      null,
    );

    const treeNodes = useMemo(() => buildSourceTree(files), [files]);

    useEffect(() => {
      onDirtyChange?.(isDirty);
    }, [isDirty, onDirtyChange]);

    const toggleFolder = (path: string) => {
      setExpandedFolders((prev) => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });
    };

    const handleSelectPath = async (path: string, currentFiles = files) => {
      setSelectedPath(path);
      // Expand parent folders
      const parts = path.split("/");
      parts.pop(); // remove filename
      if (parts.length > 0) {
        setExpandedFolders((prev) => {
          const next = new Set(prev);
          let curr = "";
          for (const p of parts) {
            curr += (curr ? "/" : "") + p;
            next.add(curr);
          }
          return next;
        });
      }

      const isFolder = currentFiles.some((f) =>
        f.relative_path.startsWith(path + "/"),
      );
      if (isFolder) {
        setFileContent("");
        return;
      }

      if (unsavedContents[path] !== undefined) {
        setFileContent(unsavedContents[path]);
        return;
      }

      const fileMeta = currentFiles.find((f) => f.relative_path === path);
      if (fileMeta) {
        try {
          const res = await fetch(fileMeta.download_url);
          if (!res.ok) throw new Error(t("sourceEditor.downloadFailed"));
          const text = await res.text();
          setFileContent(text);
        } catch (err) {
          console.error(err);
          toast.error(t("sourceEditor.loadContentFailed", { path }));
          setFileContent("");
        }
      } else {
        setFileContent("");
      }
    };

    const fetchFiles = async () => {
      try {
        let data: S3File[] = [];
        if (fileType === "code_file") {
          data = await listSourceCodeFiles(modelId);
        } else {
          data = await listReferenceFiles(modelId);
        }
        data.sort((a, b) => a.relative_path.localeCompare(b.relative_path));
        setFiles(data);

        if (data.length > 0 && !selectedPath) {
          // Auto-select first real file
          const firstFile = data.find(
            (f) => !f.relative_path.endsWith(".keep"),
          );
          if (firstFile) handleSelectPath(firstFile.relative_path, data);
        } else if (
          selectedPath &&
          !data.find((f) => f.relative_path === selectedPath) &&
          !data.find((f) => f.relative_path.startsWith(selectedPath + "/"))
        ) {
          setSelectedPath(null);
          setFileContent("");
        }
      } catch (err) {
        console.error(err);
        toast.error(t("sourceEditor.loadListFailed", { title }));
      }
    };

    useEffect(() => {
      let isMounted = true;
      const loadData = async () => {
        setLoading(true);
        await fetchFiles();
        if (isMounted) setLoading(false);
      };
      loadData();
      return () => {
        isMounted = false;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [modelId, fileType]);

    useEffect(() => {
      const handleBeforeUnload = (e: BeforeUnloadEvent) => {
        if (!isDirty) return;
        e.preventDefault();
        e.returnValue = "";
      };
      window.addEventListener("beforeunload", handleBeforeUnload);
      return () =>
        window.removeEventListener("beforeunload", handleBeforeUnload);
    }, [isDirty]);

    const handleEditorChange = (value: string | undefined) => {
      const val = value || "";
      setFileContent(val);
      if (selectedPath) {
        setUnsavedContents((prev) => ({ ...prev, [selectedPath]: val }));
      }
    };

    const handleSave = async (): Promise<boolean> => {
      if (Object.keys(unsavedContents).length === 0) return true;
      try {
        setSaving(true);
        const promises = Object.entries(unsavedContents).map(
          async ([path, content]) => {
            const blob = new Blob([content], { type: "text/plain" });
            const file = new File([blob], path.split("/").pop() || "file.txt");

            if (fileType === "code_file") {
              await uploadSourceCodeFile(modelId, file, path);
            } else {
              await uploadReferenceFile(modelId, file, path);
            }
          },
        );

        await Promise.all(promises);
        setUnsavedContents({});
        toast.success(t("sourceEditor.saved", { title }));
        await fetchFiles();
        return true;
      } catch (err) {
        console.error(err);
        toast.error(t("sourceEditor.saveFailed", { title }));
        return false;
      } finally {
        setSaving(false);
      }
    };

    useImperativeHandle(ref, () => ({ save: handleSave }));

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const uploadedFiles = e.target.files;
      if (!uploadedFiles || uploadedFiles.length === 0) return;

      const filesArray = Array.from(uploadedFiles);
      try {
        setSaving(true);
        let prefix = "";
        if (selectedPath) {
          const isFolder = files.some((f) =>
            f.relative_path.startsWith(selectedPath + "/"),
          );
          if (isFolder) {
            prefix = selectedPath + "/";
          } else {
            const parts = selectedPath.split("/");
            parts.pop();
            if (parts.length > 0) prefix = parts.join("/") + "/";
          }
        }

        const promises = filesArray.map(async (file) => {
          const path = prefix + file.name;
          if (fileType === "code_file") {
            await uploadSourceCodeFile(modelId, file, path);
          } else {
            await uploadReferenceFile(modelId, file, path);
          }
        });

        await Promise.all(promises);
        toast.success(t("sourceEditor.uploaded", { count: filesArray.length }));
        await fetchFiles();
      } catch (err) {
        console.error(err);
        toast.error(t("sourceEditor.uploadFailed"));
      } finally {
        setSaving(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    };

    const startCreateFile = () => {
      let parentPath = "";
      if (selectedPath) {
        const isFolder = files.some((f) =>
          f.relative_path.startsWith(selectedPath + "/"),
        );
        if (isFolder) {
          parentPath = selectedPath;
        } else {
          const parts = selectedPath.split("/");
          parts.pop();
          if (parts.length > 0) parentPath = parts.join("/");
        }
      }
      setCreatingFile({ type: "file", parentPath });
      if (parentPath) {
        setExpandedFolders((prev) => new Set(prev).add(parentPath));
      }
    };

    const startCreateFolder = () => {
      let parentPath = "";
      if (selectedPath) {
        const isFolder = files.some((f) =>
          f.relative_path.startsWith(selectedPath + "/"),
        );
        if (isFolder) {
          parentPath = selectedPath;
        } else {
          const parts = selectedPath.split("/");
          parts.pop();
          if (parts.length > 0) parentPath = parts.join("/");
        }
      }
      setCreatingFile({ type: "folder", parentPath });
      if (parentPath) {
        setExpandedFolders((prev) => new Set(prev).add(parentPath));
      }
    };

    const finishCreate = async (name: string) => {
      const creating = creatingFile;
      setCreatingFile(null);
      if (!name || !creating) return;

      const { type, parentPath } = creating;
      const path = parentPath ? `${parentPath}/${name}` : name;

      if (type === "file") {
        setUnsavedContents((prev) => ({ ...prev, [path]: "" }));
        const virtualFile: S3File = {
          key: path,
          relative_path: path,
          size_bytes: 0,
          updated_at: new Date().toISOString(),
          download_url: "",
        };
        setFiles((prev) => [
          ...prev.filter((f) => f.relative_path !== path),
          virtualFile,
        ]);
        handleSelectPath(path, [...files, virtualFile]);
      } else {
        const keepPath = `${path}/.keep`;
        try {
          setSaving(true);
          const emptyFile = new File([new Blob([""])], ".keep");
          if (fileType === "code_file") {
            await uploadSourceCodeFile(modelId, emptyFile, keepPath);
          } else {
            await uploadReferenceFile(modelId, emptyFile, keepPath);
          }
          toast.success(t("sourceEditor.folderCreated", { name }));
          await fetchFiles();
          setExpandedFolders((prev) => new Set(prev).add(path));
        } catch (err) {
          console.error(err);
          toast.error(t("sourceEditor.folderCreateFailed"));
        } finally {
          setSaving(false);
        }
      }
    };

    const handleDelete = () => {
      if (!selectedPath) return;
      setDeleteConfirmPath(selectedPath);
    };

    const confirmDelete = async () => {
      if (!deleteConfirmPath) return;

      const isFolder = files.some((f) =>
        f.relative_path.startsWith(deleteConfirmPath + "/"),
      );

      try {
        setSaving(true);
        const pathToDelete = isFolder
          ? `${deleteConfirmPath}/`
          : deleteConfirmPath;
        if (fileType === "code_file") {
          await deleteSourceCodeFile(modelId, pathToDelete);
        } else {
          await deleteReferenceFile(modelId, pathToDelete);
        }

        if (unsavedContents[deleteConfirmPath]) {
          setUnsavedContents((prev) => {
            const next = { ...prev };
            delete next[deleteConfirmPath];
            return next;
          });
        }

        toast.success(
          isFolder
            ? t("sourceEditor.folderDeleted")
            : t("sourceEditor.fileDeleted"),
        );
        if (
          selectedPath === deleteConfirmPath ||
          selectedPath?.startsWith(deleteConfirmPath + "/")
        ) {
          setSelectedPath(null);
          setFileContent("");
        }
        await fetchFiles();
      } catch (err) {
        console.error(err);
        toast.error(t("sourceEditor.deleteFailed"));
      } finally {
        setSaving(false);
        setDeleteConfirmPath(null);
      }
    };

    const getLanguage = (path: string) => {
      if (path.endsWith(".py")) return "python";
      if (path.endsWith(".json")) return "json";
      if (path.endsWith(".js")) return "javascript";
      if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
      if (path.endsWith(".md")) return "markdown";
      if (path.endsWith(".yml") || path.endsWith(".yaml")) return "yaml";
      if (path.endsWith(".sh")) return "shell";
      return "plaintext";
    };

    const isCsv = selectedPath?.endsWith(".csv");
    const isSelectedFolder = selectedPath
      ? files.some((f) => f.relative_path.startsWith(selectedPath + "/"))
      : false;

    if (loading) {
      return (
        <div className="flex h-125 border border-border rounded-surface bg-surface mb-6 items-center justify-center shadow-sm">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
        </div>
      );
    }

    return (
      <div className="flex flex-col h-125 border border-border rounded-surface overflow-hidden bg-surface shadow-sm">
        <div className="flex border-b border-border bg-muted">
          <div className="flex-1 flex items-center justify-between p-3">
            <div className="text-style-body-strong text-color-foreground flex items-center gap-2">
              {icon}
              {title}
              {isDirty && (
                <span
                  className="ml-1 inline-block h-2 w-2 rounded-full bg-warning"
                  title={t("sourceEditor.unsaved")}
                />
              )}
            </div>
            <div className="flex items-center gap-1">
              {onSetEntryPoint &&
                selectedPath?.endsWith(entryPointExtension) && (
                  <button
                    className={`px-3 py-2 text-style-caption rounded-control font-medium mr-2 flex items-center gap-1 transition-colors ${
                      currentEntryPoint === selectedPath
                        ? "bg-primary text-color-primary-foreground shadow-sm hover:bg-primary-hover"
                        : "bg-primary-subtle text-color-primary hover:bg-primary/15 border border-primary/20"
                    }`}
                    onClick={() => onSetEntryPoint(selectedPath)}
                    title={setAsMainLabel ?? t("sourceEditor.mainTitle")}
                  >
                    <Play className="w-3 h-3" />
                    {currentEntryPoint === selectedPath
                      ? t("sourceEditor.selected")
                      : (setAsMainLabel ?? t("sourceEditor.setMain"))}
                  </button>
                )}

              <Button
                variant="primary"
                size="sm"
                onClick={handleSave}
                disabled={saving || !isDirty}
                loading={saving}
                title={t("sourceEditor.saveChanges")}
              >
                <Save className="w-4 h-4 mr-1.5" />
                {t("sourceEditor.save")}
              </Button>
            </div>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 bg-surface flex flex-col min-w-0">
            {!selectedPath || isSelectedFolder ? (
              <div className="flex-1 flex flex-col p-6 bg-surface">
                {files.length === 0 ? (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex-1 w-full flex flex-col items-center justify-center border-2 border-dashed border-border rounded-surface hover:bg-muted hover:border-primary transition-colors group cursor-pointer"
                  >
                    <Upload className="w-12 h-12 mb-4 text-color-muted-foreground group-hover:text-color-primary transition-colors" />
                    <p className="text-color-muted-foreground font-medium text-style-heading group-hover:text-color-primary transition-colors">
                      {t("sourceEditor.uploadPrompt")}
                    </p>
                    <p className="text-style-body text-color-muted-foreground mt-2">
                      {t("sourceEditor.support", { types: accept })}
                    </p>
                  </button>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-color-muted-foreground">
                    <FolderOpen className="w-12 h-12 mb-4 text-color-muted-foreground" />
                    <p>{t("sourceEditor.selectFile")}</p>
                  </div>
                )}
              </div>
            ) : editorType === "csv" || isCsv ? (
              <CSVEditor
                initialCsvText={fileContent}
                onChange={handleEditorChange}
              />
            ) : (
              <LazyCodeEditor
                height="100%"
                language={getLanguage(selectedPath)}
                theme={resolvedTheme === "dark" ? "vs-dark" : "vs"}
                value={fileContent}
                onChange={handleEditorChange}
                options={{
                  minimap: { enabled: false },
                  // typography-ignore: Monaco requires a numeric pixel value.
                  fontSize: 14,
                  wordWrap: "on",
                  scrollBeyondLastLine: false,
                }}
              />
            )}
          </div>

          <div className="w-75 border-l border-border bg-muted flex flex-col shrink-0">
            <div className="flex items-center justify-between p-2 border-b border-border text-color-muted-foreground">
              <span className="text-style-overline uppercase pl-2 text-color-muted-foreground">
                {t("sourceEditor.explorer")}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={startCreateFile}
                  title={t("sourceEditor.newFile")}
                  className="rounded-surface p-1 text-color-foreground hover:bg-muted"
                >
                  <FilePlus className="w-4 h-4" />
                </button>
                <button
                  onClick={startCreateFolder}
                  title={t("sourceEditor.newFolder")}
                  className="rounded-surface p-1 text-color-foreground hover:bg-muted"
                >
                  <FolderPlus className="w-4 h-4" />
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  title={t("sourceEditor.uploadFiles")}
                  className="rounded-surface p-1 text-color-foreground hover:bg-muted"
                >
                  <Upload className="w-4 h-4" />
                </button>
                <button
                  onClick={handleDelete}
                  title={t("sourceEditor.deleteSelected")}
                  disabled={!selectedPath}
                  className="rounded-surface p-1 text-color-danger hover:bg-muted hover:text-color-danger/80 disabled:opacity-30"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <input
              type="file"
              multiple
              className="hidden"
              accept={accept}
              ref={fileInputRef}
              onChange={handleUpload}
            />

            <div className="flex-1 overflow-y-auto py-2 pr-2">
              {files.length === 0 && !creatingFile ? (
                <div className="text-style-body text-color-muted-foreground text-center py-8">
                  {t("sourceEditor.noFiles")}
                </div>
              ) : (
                <SourceTree
                  nodes={treeNodes}
                  selectedPath={selectedPath}
                  onSelect={handleSelectPath}
                  unsavedContents={unsavedContents}
                  currentEntryPoint={currentEntryPoint}
                  expandedFolders={expandedFolders}
                  toggleFolder={toggleFolder}
                  creatingFile={creatingFile}
                  onFinishCreating={finishCreate}
                  currentParentPath=""
                />
              )}
            </div>
          </div>
        </div>

        <ConfirmModal
          open={!!deleteConfirmPath}
          title={t("sourceEditor.deleteTitle")}
          description={
            deleteConfirmPath ? (
              <p>
                {t("sourceEditor.deleteQuestion", {
                  kind: files.some((f) =>
                    f.relative_path.startsWith(deleteConfirmPath + "/"),
                  )
                    ? t("sourceEditor.folder")
                    : t("sourceEditor.file"),
                  path: deleteConfirmPath,
                })}
                <br />
                {t("sourceEditor.deleteDescription")}
              </p>
            ) : null
          }
          tone="danger"
          confirmText={t("sourceEditor.delete")}
          loading={saving}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteConfirmPath(null)}
        />
      </div>
    );
  },
);

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Download,
  Eye,
  FileCode2,
  FilePlus,
  FolderOpen,
  FolderPlus,
  HelpCircle,
  KeyRound,
  PenLine,
  Play,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";
import { Loading } from "@/shared/components/Loading";
import BaseDialog from "@/shared/components/BaseDialog";
import { Input } from "@/shared/components/Input";
import { DirectoryTree } from "@/shared/components/DirectoryTree";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageTabs } from "@/shared/components/PageTabs";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { InputFileDialog, type InputFileSelection } from "./InputFileDialog";
import { HelpDialog } from "./HelpDialog";
import { FileViewer } from "./FileViewer";
import {
  deleteJobEntry,
  downloadWorkspaceSelection,
  downloadRunOutput,
  getRunFile,
  readEntry,
  saveJobEntry,
  updateJobWorkspace,
  type JobWorkspace,
  type WorkspaceEntry,
} from "@/features/training/api/jobWorkspaceApi";
import { droppedEntries, kindForPath, workspaceTree, isReadableFile } from "@/features/training/lib/workspaceFiles";
import { hasDownloadableFiles, saveDownload } from "@/features/training/lib/downloadSelection";
import type { TrainingOutput } from "@/features/training/types";

export interface WorkspaceEditorHandle {
  saveAll: () => Promise<number>;
}

interface Props {
  workspace: JobWorkspace;
  entries: WorkspaceEntry[];
  outputs?: TrainingOutput[];
  runId?: string;
  entryPoint: string;
  readOnly: boolean;
  onRefresh: () => Promise<JobWorkspace>;
  onDirty: (dirty: boolean) => void;
  externallyBusy?: boolean;
  onBusy: (busy: boolean) => void;
  onOpenEnvironment?: () => void;
  onDeleteOutputs?: () => Promise<void>;
}

export const WorkspaceEditor = forwardRef<WorkspaceEditorHandle, Props>(function WorkspaceEditor(
  {
    workspace,
    entries,
    outputs = [],
    runId,
    entryPoint,
    readOnly,
    externallyBusy = false,
    onRefresh,
    onDirty,
    onBusy,
    onOpenEnvironment,
    onDeleteOutputs,
  },
  ref,
) {
  const { t } = useTranslation("training");
  const [activeTab, setActiveTab] = useState<"input" | "output">("input");
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null);
  const [contents, setContents] = useState<Record<string, string>>({});
  const [outputContents, setOutputContents] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState<Record<string, string>>({});
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const workspaceRef = useRef(workspace);
  workspaceRef.current = workspace;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [expandedOutputFolders, setExpandedOutputFolders] = useState<Set<string>>(new Set());
  const [localBusy, setBusy] = useState(false);
  const busy = localBusy || externallyBusy;
  const [dialog, setDialog] = useState<"new" | "edit" | "folder" | null>(null);
  const [folderName, setFolderName] = useState("");
  const [folderParent, setFolderParent] = useState("");
  const [folderError, setFolderError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [removeAllOpen, setRemoveAllOpen] = useState(false);
  const [resetAllOpen, setResetAllOpen] = useState(false);
  const [deletingOutputs, setDeletingOutputs] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const needsReload = useRef(false);
  const [preview, setPreview] = useState(false);
  const [outputPreview, setOutputPreview] = useState(false);

  const file = entries.find((entry) => entry.path === selected);
  const parent = file?.kind === "folder" ? file.path : selected?.includes("/") ? selected.slice(0, selected.lastIndexOf("/")) : "";
  const nodes = useMemo(() => workspaceTree(entries), [entries]);

  const outputNodes = useMemo(() => {
    const virtualEntries: WorkspaceEntry[] = (outputs ?? []).map((out) => ({
      id: out.id,
      path: out.relative_path,
      kind: out.relative_path.endsWith(".csv") ? "data" : out.relative_path.endsWith(".py") ? "script" : "document",
      size_bytes: out.size_bytes,
      download_url: "",
    }));
    return workspaceTree([{ id: "model-root", path: "Model", kind: "folder", size_bytes: 0 }, { id: "metadata-root", path: "Metadata", kind: "folder", size_bytes: 0 }, ...virtualEntries]);
  }, [outputs]);

  const selectedOutputNode = useMemo(() => {
    if (!selectedOutput) return null;
    return outputs.find((out) => out.relative_path === selectedOutput) || null;
  }, [outputs, selectedOutput]);

  const scope = runId ?? workspace.id;
  const loadedScope = useRef(scope);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const key = (path: string) => `${scope}:${path}`;
  const selectedText = selected ? dirty[selected] ?? contents[key(selected)] ?? "" : "";
  const outputContent = selectedOutputNode ? outputContents[selectedOutputNode.id] ?? "" : "";

  useEffect(() => {
    onDirty(Object.keys(dirty).length > 0);
  }, [dirty, onDirty]);

  // Load input file content
  useEffect(() => {
    if (!file || file.kind === "folder" || contents[`${scope}:${file.path}`] !== undefined) return;
    let alive = true;
    const requestedScope = scope;
    void (runId ? getRunFile(runId, file.path) : readEntry(file))
      .then((content) => {
        if (alive && currentScope.current === requestedScope) {
          setContents((current) => ({ ...current, [`${scope}:${file.path}`]: content }));
        }
      })
      .catch((error) => {
        if (alive) toast.error(getApiErrorMessage(error, t("studio.failed")));
      });
    return () => {
      alive = false;
    };
  }, [file, runId, scope, contents, t]);

  // Load output file content if readable
  useEffect(() => {
    if (!selectedOutputNode || !runId || !isReadableFile(selectedOutputNode.relative_path, selectedOutputNode.size_bytes)) return;
    if (outputContents[selectedOutputNode.id] !== undefined) return;
    let alive = true;
    void downloadRunOutput(runId, selectedOutputNode.id)
      .then(async (url) => {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch output file");
        const text = /\.(png|jpe?g)$/i.test(selectedOutputNode.relative_path)
          ? await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; void res.blob().then(blob => reader.readAsDataURL(blob)).catch(reject); })
          : await res.text();
        if (alive) {
          setOutputContents((prev) => ({ ...prev, [selectedOutputNode.id]: text }));
        }
      })
      .catch((error) => {
        if (alive) toast.error(getApiErrorMessage(error, t("studio.failed")));
      });
    return () => {
      alive = false;
    };
  }, [selectedOutputNode, runId, outputContents, t]);

  async function refresh() {
    const next = await onRefresh();
    workspaceRef.current = next;
    return next;
  }

  async function saveAll() {
    if (needsReload.current) throw new Error(t("studio.reload"));
    if (readOnly && Object.keys(dirtyRef.current).length) throw new Error(t("studio.locked"));
    let revision = workspaceRef.current.revision;
    for (const [path, content] of Object.entries(dirtyRef.current)) {
      const entry = workspaceRef.current.entries.find((item) => item.path === path);
      if (!entry || entry.kind === "folder") throw new Error(t("studio.reload"));
      let result;
      try {
        result = await saveJobEntry(workspace.id, revision, { path, kind: entry.kind, file: null }, entry.id, content);
      } catch (error) {
        needsReload.current = true;
        throw error;
      }
      revision = result.revision;
      workspaceRef.current = { ...workspaceRef.current, revision };
      setContents((current) => ({ ...current, [key(path)]: content }));
      setDirty((current) => {
        const next = { ...current };
        delete next[path];
        return next;
      });
      const remaining = { ...dirtyRef.current };
      delete remaining[path];
      dirtyRef.current = remaining;
    }
    if (revision !== workspace.revision) await refresh();
    return revision;
  }

  useImperativeHandle(ref, () => ({ saveAll }));

  // Shortcut Ctrl+S / Cmd+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (!readOnly && !busy && Object.keys(dirtyRef.current).length > 0) {
          void task(async () => {
            await saveAll();
            toast.success(t("studio.saved", "All changes saved."));
          });
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  async function task(action: () => Promise<void>, invalidateOnError = true) {
    if (busy || externallyBusy) return;
    setBusy(true);
    onBusy(true);
    try {
      await action();
    } catch (error) {
      if (invalidateOnError) needsReload.current = true;
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }

  async function cleanDraft() {
    await saveAll();
    return workspaceRef.current;
  }

  async function saveSelection(selection: InputFileSelection) {
    await task(async () => {
      const current = await cleanDraft();
      await saveJobEntry(workspace.id, current.revision, selection, dialog === "edit" ? file?.id : undefined);
      setDialog(null);
      setSelected(selection.path);
      setContents({});
      await refresh();
    });
  }

  async function move(path: string, folder: string) {
    if (readOnly || path === "requirements.txt") return;
    await task(async () => {
      const current = await cleanDraft();
      const entry = current.entries.find((item) => item.path === path);
      if (!entry) return;
      const destination = folder ? `${folder}/${path.split("/").pop()}` : path.split("/").pop()!;
      if (destination === path) return;
      await saveJobEntry(workspace.id, current.revision, { path: destination, kind: entry.kind, file: null }, entry.id);
      setSelected(destination);
      setContents({});
      await refresh();
    });
  }

  function drop(event: DragEvent, folder: string) {
    if (readOnly || busy) return;
    const internal = event.dataTransfer.getData("application/x-training-path");
    if (internal) {
      void move(internal, folder);
      return;
    }
    const dropped = droppedEntries(event);
    void task(async () => {
      let current = await cleanDraft();
      const incoming = await dropped;
      const known = new Set(current.entries.map((entry) => entry.path));
      for (const item of incoming) {
        const path = folder ? `${folder}/${item.path}` : item.path;
        const kind = item.file ? kindForPath(path) : "folder";
        if (known.has(path)) {
          if (kind === "folder" && current.entries.some((entry) => entry.path === path && entry.kind === "folder")) continue;
          throw new Error(t("studio.pathExists", { path }));
        }
        const result = await saveJobEntry(
          workspace.id,
          current.revision,
          item.file ? { path, kind: kindForPath(path), file: item.file } : { path, kind: "folder", file: null },
        );
        current = { ...current, revision: result.revision };
        workspaceRef.current = current;
        known.add(path);
      }
      await refresh();
    });
  }

  const canDownloadInput = hasDownloadableFiles(entries.filter((entry) => entry.kind !== "folder").map((entry) => entry.path), selected);
  const canDownloadOutput = !workspace.outputs_purged_at && hasDownloadableFiles(outputs.map((output) => output.relative_path), selectedOutput);

  async function download() {
    if (!canDownloadInput) return;
    const current = runId ? workspace : await cleanDraft();
    saveDownload(await downloadWorkspaceSelection(workspace.id, "input", selected, runId ? undefined : current.revision));
  }

  async function handleDownloadOutput(item?: TrainingOutput | null) {
    if (!canDownloadOutput) return;
    saveDownload(await downloadWorkspaceSelection(workspace.id, "outputs", item?.relative_path ?? selectedOutput));
  }

  async function removeAll() {
    if (readOnly || busy) return;
    await task(async () => {
      let current = await cleanDraft();
      for (const entry of [...current.entries]) {
        try {
          const res = await deleteJobEntry(workspace.id, entry.id, current.revision);
          current = { ...current, revision: res.revision };
          workspaceRef.current = current;
        } catch {
          // ignore already deleted children
        }
      }
      setSelected(null);
      setContents({});
      setDirty({});
      dirtyRef.current = {};
      setRemoveAllOpen(false);
      await refresh();
      toast.success(t("studio.allFilesDeleted"));
    });
  }

  function resetAll() {
    setDirty({});
    dirtyRef.current = {};
    setContents({});
    setResetAllOpen(false);
    toast.success(t("studio.resetAllSuccess"));
  }

  if (loadedScope.current !== scope) loadedScope.current = scope;

  return (
    <div className="rounded-surface border border-border bg-surface overflow-hidden shadow-sm">
      {/* Top Header Toolbar */}
      <div className="grid border-b border-border bg-surface md:grid-cols-[minmax(0,1fr)_18rem]">
        {/* Left Column (Editor Header): File Name on left, Action Buttons on right */}
        <div className="flex flex-wrap items-center justify-between px-3 py-1.5 gap-2 min-w-0">
          {/* Left: Selected File Name / Dirty Indicator */}
          <div className="flex items-center gap-1 font-mono text-style-body font-medium text-color-foreground pl-1 min-w-0">
            {activeTab === "input" && selected ? (
              <>
                <span className="truncate max-w-60">{selected}</span>
                {dirty[selected] !== undefined && (
                  <span
                    className="text-color-danger font-bold text-style-body"
                    title={t("studio.unsaved")}
                  >
                    *
                  </span>
                )}
              </>
            ) : activeTab === "output" && selectedOutputNode ? (
              <span className="truncate max-w-60">{selectedOutputNode.relative_path}</span>
            ) : null}
          </div>

          {/* Right: Editor Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            {activeTab === "input" ? (
              <>
                {/* Save as Main (Python scripts only) */}
                {file?.kind === "script" && (
                  <Button
                    size="sm"
                    variant={entryPoint === file.path ? "primary" : "secondary"}
                    icon={<Play className="h-3.5 w-3.5" />}
                    disabled={readOnly || busy || entryPoint === file.path}
                    onClick={() =>
                      void task(async () => {
                        const current = await cleanDraft();
                        await updateJobWorkspace(workspace.id, current.revision, {
                          entry_point: file.path,
                        });
                        await refresh();
                      })
                    }
                    title={entryPoint === file.path ? t("studio.isMain") : t("studio.saveAsMain")}
                  >
                    {entryPoint === file.path ? t("studio.isMain") : t("studio.saveAsMain")}
                  </Button>
                )}

                {/* Markdown Preview (.md documents only) */}
                {file?.kind === "document" && (
                  <Button
                    size="sm"
                    variant={preview ? "primary" : "secondary"}
                    icon={<Eye className="h-4 w-4" />}
                    onClick={() => setPreview(!preview)}
                  >
                    {t(preview ? "studio.editor" : "studio.markdownPreview")}
                  </Button>
                )}

                {/* Save all (Ctrl+S) */}
                <Button
                  size="sm"
                  icon={<Save className="h-4 w-4" />}
                  disabled={readOnly || busy || !Object.keys(dirty).length}
                  onClick={() =>
                    void task(async () => {
                      await saveAll();
                    })
                  }
                  title={`${t("studio.saveAll")} (Ctrl+S)`}
                >
                  {t("studio.saveAll")}
                </Button>

                {/* Remove all */}
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Trash2 className="h-4 w-4" />}
                  disabled={readOnly || busy || !entries.length}
                  onClick={() => setRemoveAllOpen(true)}
                  title={t("studio.removeAll")}
                >
                  {t("studio.removeAll")}
                </Button>

                {/* Reset all */}
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<RotateCcw className="h-4 w-4" />}
                  disabled={readOnly || busy || !Object.keys(dirty).length}
                  onClick={() => setResetAllOpen(true)}
                  title={t("studio.resetAll")}
                >
                  {t("studio.resetAll")}
                </Button>

                {/* Environment & Secrets */}
                {onOpenEnvironment && (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<KeyRound className="h-4 w-4" />}
                    disabled={readOnly || busy}
                    onClick={onOpenEnvironment}
                  >
                    {t("studio.environment")}
                  </Button>
                )}

                {/* Help */}
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<HelpCircle className="h-4 w-4" />}
                  onClick={() => setHelpOpen(true)}
                >
                  {t("studio.help")}
                </Button>
              </>
            ) : (
              selectedOutput?.endsWith(".md") && (
                <Button
                  size="sm"
                  variant={outputPreview ? "primary" : "secondary"}
                  icon={<Eye className="h-4 w-4" />}
                  onClick={() => setOutputPreview(!outputPreview)}
                >
                  {t(outputPreview ? "studio.editor" : "studio.markdownPreview")}
                </Button>
              )
            )}
          </div>
        </div>

        {/* Right Column (DirectoryTree Header Top): PageTabs above DirectoryTree */}
        <div className="flex items-center justify-end px-3 py-1.5 border-t md:border-t-0 md:border-l border-border bg-surface">
          <PageTabs
            tabs={[
              {
                label: t("studio.input"),
                isActive: activeTab === "input",
                onClick: () => setActiveTab("input"),
              },
              {
                label: t("studio.output", "Output"),
                isActive: activeTab === "output",
                onClick: () => setActiveTab("output"),
              },
            ]}
          />
        </div>
      </div>

      {/* Main Grid: Left = Viewer, Right = DirectoryTree Explorer */}
      <div className="grid min-h-125 md:grid-cols-[minmax(0,1fr)_18rem]">
        {/* LEFT: Viewer Area */}
        <div className="flex min-w-0 flex-1 flex-col bg-surface h-full">
          {activeTab === "input" ? (
            entries.length === 0 ? (
              <div className="flex flex-1 flex-col p-4 h-full">
                <Placeholder
                  className="h-full w-full flex-1"
                  icon={<FolderOpen className="h-12 w-12 text-color-muted-foreground" />}
                  title={t("studio.noFiles")}
                  description={t("studio.createFirstFile")}
                  action={
                    <Button
                      variant="primary"
                      icon={<Plus className="h-4 w-4" />}
                      disabled={readOnly || busy}
                      onClick={() => setDialog("new")}
                    >
                      {t("workspace.fileDialog.create")}
                    </Button>
                  }
                />
              </div>
            ) : !file || file.kind === "folder" ? (
              <div className="flex flex-1 flex-col p-4 h-full">
                <Placeholder
                  className="h-full w-full flex-1"
                  icon={<FolderOpen className="h-12 w-12 text-color-muted-foreground" />}
                  title={t("studio.selectFile")}
                  description={t("studio.selectFileHint")}
                />
              </div>
            ) : contents[key(file.path)] === undefined ? (
              <div className="flex flex-1 flex-col p-4 h-full">
                <Placeholder className="h-full w-full flex-1">
                  <Loading size="lg" text={t("studio.loadingFile")} />
                </Placeholder>
              </div>
            ) : (
              <FileViewer
                path={file.path}
                content={selectedText}
                readOnly={readOnly || busy}
                showMarkdownPreview={preview}
                onChange={(value) => {
                  if (!readOnly && file) {
                    setDirty((current) => ({ ...current, [file.path]: value }));
                  }
                }}
              />
            )
          ) : outputs.length === 0 ? (
            <div className="flex flex-1 flex-col p-4 h-full">
              <Placeholder
                className="h-full w-full flex-1"
                icon={<FolderOpen className="h-12 w-12 text-color-muted-foreground" />}
                title={t("studio.noOutput")}
                description={t("studio.noOutputDescription")}
              />
            </div>
          ) : !selectedOutputNode ? (
            <div className="flex flex-1 flex-col p-4 h-full">
              <Placeholder
                className="h-full w-full flex-1"
                icon={<FolderOpen className="h-12 w-12 text-color-muted-foreground" />}
                title={t("studio.selectFile")}
                description={t("studio.selectFileHint")}
              />
            </div>
          ) : !isReadableFile(selectedOutputNode.relative_path, selectedOutputNode.size_bytes) ? (
            <div className="flex flex-1 flex-col p-4 h-full">
              <Placeholder
                className="h-full w-full flex-1"
                icon={<FileCode2 className="h-12 w-12 text-color-muted-foreground" />}
                title={selectedOutputNode.relative_path.split("/").pop()}
                description={t("studio.unsupportedPreview")}
                action={
                  <Button
                    variant="primary"
                    icon={<Download className="h-4 w-4" />}
                    onClick={() => void task(() => handleDownloadOutput(selectedOutputNode), false)}
                  >
                    {t("studio.download")}
                  </Button>
                }
              />
            </div>
          ) : outputContents[selectedOutputNode.id] === undefined ? (
            <div className="flex flex-1 flex-col p-4 h-full">
              <Placeholder className="h-full w-full flex-1">
                <Loading size="lg" text={t("studio.loadingFile")} />
              </Placeholder>
            </div>
          ) : (
            <FileViewer
              path={selectedOutputNode.relative_path}
              content={outputContent}
              readOnly={true}
              showMarkdownPreview={outputPreview}
            />
          )}
        </div>

        {/* RIGHT: DirectoryTree Explorer */}
        <div className="flex flex-col border-l border-border bg-surface shrink-0">
          {/* Explorer Header */}
          <div className="flex items-center justify-between border-b border-border p-2 text-color-muted-foreground">
            <span className="pl-2 text-style-overline uppercase text-color-muted-foreground font-semibold">
              {activeTab === "input" ? t("studio.input") : t("studio.output", "Output")}
            </span>
            <div className="flex items-center gap-1">
              {activeTab === "input" ? (
                <>
                  <button
                    type="button"
                    onClick={() => setDialog("new")}
                    title={t("workspace.fileDialog.create")}
                    disabled={readOnly || busy}
                    className="rounded-surface p-1.5 text-color-foreground hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <FilePlus className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setFolderName("");
                      setFolderParent(parent);
                      setFolderError("");
                      setDialog("folder");
                    }}
                    title={t("studio.newFolder")}
                    disabled={readOnly || busy}
                    className="rounded-surface p-1.5 text-color-foreground hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <FolderPlus className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (selected && file && file.kind !== "folder") {
                        setDialog("edit");
                      }
                    }}
                    title={t("studio.edit")}
                    aria-label={t("studio.edit")}
                    disabled={readOnly || busy || !selected || !file || file.kind === "folder"}
                    className="rounded-surface p-1.5 text-color-foreground hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <PenLine className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void task(download, false)}
                    title={t("studio.download")}
                    aria-label={t("studio.download")}
                    disabled={busy || !canDownloadInput}
                    className="rounded-surface p-1.5 text-color-foreground hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleting(true)}
                    title={t("studio.delete")}
                    disabled={readOnly || busy || !selected}
                    className="rounded-surface p-1.5 text-color-danger hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => void task(() => handleDownloadOutput(), false)}
                    title={t("studio.download")}
                    aria-label={t("studio.download")}
                    disabled={busy || !canDownloadOutput}
                    className="rounded-surface p-1.5 text-color-foreground hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeletingOutputs(true)}
                    title={t("studio.delete")}
                    disabled={busy || !outputs.length}
                    className="rounded-surface p-1.5 text-color-danger hover:bg-surface-hover disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </>
              )}
            </div>
          </div>

          {/* DirectoryTree with Drag & Drop */}
          <div
            className="flex-1 overflow-y-auto p-2"
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                if (activeTab === "input") setSelected(null); else setSelectedOutput(null);
              }
            }}
            onDragOver={activeTab === "input" && !readOnly ? (event) => event.preventDefault() : undefined}
            onDrop={activeTab === "input" && !readOnly ? (event) => { event.preventDefault(); drop(event, ""); } : undefined}
          >
            {activeTab === "input" ? (
              nodes.length === 0 ? (
                <p className="p-4 text-center text-style-caption text-color-muted-foreground">
                  {t("studio.noFiles")}
                </p>
              ) : (
                <DirectoryTree
                  nodes={nodes}
                  selectedPath={selected}
                  onSelect={(path) => setSelected((current) => current === path ? null : path)}
                  unsavedContents={dirty}
                  currentEntryPoint={entryPoint}
                  expandedFolders={expanded}
                  toggleFolder={(path) =>
                    setExpanded((current) => {
                      const next = new Set(current);
                      if (next.has(path)) next.delete(path);
                      else next.add(path);
                      return next;
                    })
                  }
                  onEditFile={!readOnly && !busy ? (path) => { setSelected(path); setDialog("edit"); } : undefined}
                  onMove={!readOnly && !busy ? (path, folder) => void move(path, folder) : undefined}
                  onDropFiles={!readOnly && !busy ? drop : undefined}
                />
              )
            ) : outputNodes.length === 0 ? (
              <p className="p-4 text-center text-style-caption text-color-muted-foreground">
                {t("studio.noOutput")}
              </p>
            ) : (
              <DirectoryTree
                nodes={outputNodes}
                selectedPath={selectedOutput}
                onSelect={(path) => setSelectedOutput((current) => current === path ? null : path)}
                unsavedContents={{}}
                expandedFolders={expandedOutputFolders}
                toggleFolder={(path) =>
                  setExpandedOutputFolders((current) => {
                    const next = new Set(current);
                    if (next.has(path)) next.delete(path);
                    else next.add(path);
                    return next;
                  })
                }
              />
            )}
          </div>
        </div>
      </div>

      {/* Dialogs */}
      {(dialog === "new" || (dialog === "edit" && file && file.kind !== "folder")) && (
        <InputFileDialog
          key={`${dialog}:${selected}`}
          existing={dialog === "edit" && file && file.kind !== "folder" ? { path: file.path, kind: file.kind } : undefined}
          parentPath={parent}
          hasRequirements={entries.some((entry) => entry.path === "requirements.txt")}
          saving={busy}
          onClose={() => setDialog(null)}
          onSave={(selection) => void saveSelection(selection)}
        />
      )}

      {dialog === "folder" && (
        <BaseDialog title={t("studio.newFolder")} onClose={() => setDialog(null)}>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const name = folderName.trim();
              if (!name || name === "." || name === ".." || /[\\/]/.test(name)
                || Array.from(name).some((character) => character.charCodeAt(0) < 32)) {
                setFolderError(t("studio.invalidFolderName"));
                return;
              }
              const path = folderParent ? `${folderParent}/${name}` : name;
              if (entries.some((entry) => entry.path === path)) {
                setFolderError(t("studio.pathExists", { path }));
                return;
              }
              void task(async () => {
                const current = await cleanDraft();
                await saveJobEntry(workspace.id, current.revision, { path, kind: "folder", file: null });
                setSelected(path);
                if (folderParent) setExpanded((current) => new Set(current).add(folderParent));
                setDialog(null);
                await refresh();
              });
            }}
          >
            <Input label={t("studio.folderName")} value={folderName} required maxLength={255} autoFocus disabled={busy}
              error={folderError || undefined} onChange={(event) => { setFolderName(event.target.value); setFolderError(""); }} />
            <div className="flex justify-end gap-3">
              <Button type="button" variant="secondary" disabled={busy} onClick={() => setDialog(null)}>{t("workspace.fileDialog.cancel")}</Button>
              <Button type="submit" loading={busy}>{t("workspace.fileDialog.createAction")}</Button>
            </div>
          </form>
        </BaseDialog>
      )}

      {/* Confirm: Delete single file */}
      <ConfirmDialog
        open={deleting}
        title={t("studio.delete")}
        description={t("studio.deleteConfirm")}
        confirmText={t("studio.delete")}
        tone="danger"
        onCancel={() => setDeleting(false)}
        onConfirm={() =>
          void task(async () => {
            const current = await cleanDraft();
            if (file) await deleteJobEntry(workspace.id, file.id, current.revision);
            setDeleting(false);
            setSelected(null);
            setContents({});
            await refresh();
          })
        }
      />

      {/* Confirm: Remove all */}
      <ConfirmDialog
        open={removeAllOpen}
        title={t("studio.removeAllTitle")}
        description={t("studio.removeAllConfirm")}
        confirmText={t("studio.removeAll")}
        tone="danger"
        onCancel={() => setRemoveAllOpen(false)}
        onConfirm={() => void removeAll()}
      />

      {/* Confirm: Reset all */}
      <ConfirmDialog
        open={resetAllOpen}
        title={t("studio.resetAllTitle")}
        description={t("studio.resetAllConfirm")}
        confirmText={t("studio.resetAll")}
        tone="danger"
        onCancel={() => setResetAllOpen(false)}
        onConfirm={resetAll}
      />

      {/* Confirm: Delete outputs */}
      <ConfirmDialog
        open={deletingOutputs}
        title={t("studio.delete")}
        description={t("studio.deleteOutputConfirm")}
        confirmText={t("studio.delete")}
        tone="danger"
        onCancel={() => setDeletingOutputs(false)}
        onConfirm={() =>
          void task(async () => {
            if (onDeleteOutputs) {
              await onDeleteOutputs();
              setSelectedOutput(null);
              setOutputContents({});
              setDeletingOutputs(false);
              toast.success(t("studio.outputDeleted"));
            }
          })
        }
      />

      {/* Help Guide Dialog */}
      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
    </div>
  );
});

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Download,
  Eye,
  FileCode2,
  FilePlus,
  FolderOpen,
  FolderPlus,
  KeyRound,
  Play,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { zipSync, strToU8, type Zippable } from "fflate";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";
import BaseDialog from "@/shared/components/BaseDialog";
import { Input } from "@/shared/components/Input";
import { DirectoryTree } from "@/shared/components/DirectoryTree";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageTabs } from "@/shared/components/PageTabs";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { TrainingFileDialog, type TrainingFileSelection } from "./TrainingFileDialog";
import { FileViewer } from "./FileViewer";
import {
  deleteJobEntry,
  downloadRunInput,
  downloadRunOutput,
  getRunFile,
  readEntry,
  saveJobEntry,
  updateJobWorkspace,
  type JobWorkspace,
  type WorkspaceEntry,
} from "@/features/training/api/jobWorkspaceApi";
import { droppedEntries, kindForPath, workspaceTree, isReadableFile } from "@/features/training/lib/workspaceFiles";
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
  const [pathValue, setPathValue] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [removeAllOpen, setRemoveAllOpen] = useState(false);
  const [resetAllOpen, setResetAllOpen] = useState(false);
  const [deletingOutputs, setDeletingOutputs] = useState(false);
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
    return workspaceTree(virtualEntries);
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
    if (!selectedOutputNode || !runId || !isReadableFile(selectedOutputNode.relative_path)) return;
    if (outputContents[selectedOutputNode.id] !== undefined) return;
    let alive = true;
    void downloadRunOutput(runId, selectedOutputNode.id)
      .then(async (url) => {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch output file");
        const text = await res.text();
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

  async function task(action: () => Promise<void>) {
    if (busy || externallyBusy) return;
    setBusy(true);
    onBusy(true);
    try {
      await action();
    } catch (error) {
      needsReload.current = true;
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

  async function saveSelection(selection: TrainingFileSelection) {
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

  async function download() {
    if (runId) {
      window.open(await downloadRunInput(runId), "_blank", "noopener,noreferrer");
      return;
    }
    const current = await cleanDraft();
    const freshFile = current.entries.find((entry) => entry.path === selected);
    if (freshFile?.kind !== "folder" && freshFile?.download_url) {
      window.open(freshFile.download_url, "_blank", "noopener,noreferrer");
      return;
    }
    const bundle: Zippable = {};
    for (const entry of current.entries) {
      if (selected && !entry.path.startsWith(selected + "/")) continue;
      bundle[entry.path + (entry.kind === "folder" ? "/" : "")] = entry.kind === "folder" ? new Uint8Array() : strToU8(await readEntry(entry));
    }
    const blob = new Blob([zipSync(bundle).slice().buffer], { type: "application/zip" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = "input.zip";
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  }

  async function handleDownloadOutput(item?: TrainingOutput | null) {
    const target = item || selectedOutputNode;
    if (!target) {
      if (outputs.length > 0) {
        const url = await downloadRunOutput(runId!, outputs[0].id);
        window.open(url, "_blank", "noopener,noreferrer");
      }
      return;
    }
    const url = await downloadRunOutput(runId!, target.id);
    window.open(url, "_blank", "noopener,noreferrer");
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
      <div className="flex flex-wrap items-center justify-between border-b border-border bg-surface px-3 py-1.5 gap-2">
        {/* Action Buttons on Far Left */}
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

          {/* Selected File Name / Dirty Indicator */}
          {activeTab === "input" && selected && (
            <div className="flex items-center gap-1.5 text-style-caption text-color-muted-foreground ml-2">
              <span className="truncate max-w-[200px]">{selected}</span>
              {dirty[selected] !== undefined && (
                <span
                  className="h-2 w-2 rounded-full bg-warning"
                  title={t("studio.unsaved")}
                />
              )}
            </div>
          )}
        </div>

        {/* PageTabs on Far Right */}
        <div className="ml-auto flex items-center">
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
      <div className="grid min-h-[500px] md:grid-cols-[minmax(0,1fr)_18rem]">
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
                      icon={<FilePlus className="h-4 w-4" />}
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
            ) : (
              <FileViewer
                path={file.path}
                content={selectedText}
                readOnly={readOnly || busy || contents[key(file.path)] === undefined}
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
          ) : !isReadableFile(selectedOutputNode.relative_path) ? (
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
                    onClick={() => void handleDownloadOutput(selectedOutputNode)}
                  >
                    {t("studio.download")}
                  </Button>
                }
              />
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
                      setPathValue(parent ? parent + "/" : "");
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
                    onClick={() => void task(download)}
                    title={t("studio.download")}
                    disabled={busy}
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
                    onClick={() => void handleDownloadOutput()}
                    title={t("studio.download")}
                    disabled={busy || (!selectedOutput && !outputs.length)}
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
                  onSelect={setSelected}
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
                onSelect={setSelectedOutput}
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
        <TrainingFileDialog
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
              void task(async () => {
                const current = await cleanDraft();
                await saveJobEntry(workspace.id, current.revision, { path: pathValue.trim(), kind: "folder", file: null });
                setDialog(null);
                await refresh();
              });
            }}
          >
            <Input label={t("studio.folderPath")} value={pathValue} onChange={(event) => setPathValue(event.target.value)} />
            <Button type="submit" disabled={busy}>{t("studio.save")}</Button>
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
    </div>
  );
});

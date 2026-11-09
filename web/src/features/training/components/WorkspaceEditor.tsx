import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { Download, FilePlus, FolderPlus, Move, Play, Save, Trash2 } from "lucide-react";
import { zipSync, strToU8, type Zippable } from "fflate";
import { Button } from "@/shared/components/Button";
import BaseDialog from "@/shared/components/BaseDialog";
import { Input } from "@/shared/components/Input";
import { DirectoryTree } from "@/shared/components/DirectoryTree";
import { CodeViewer } from "@/shared/components/CodeViewer";
import { DataViewer } from "@/shared/components/DataViewer";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { TrainingFileDialog, type TrainingFileSelection } from "./TrainingFileDialog";
import { MarkdownPreview } from "./MarkdownPreview";
import { deleteWorkspaceEntry, downloadRunInput, getRunFile, readEntry, saveWorkspaceEntry, updateWorkspace, type TrainingWorkspace, type WorkspaceEntry } from "@/features/training/api/workspacesApi";
import { droppedEntries, kindForPath, workspaceTree } from "@/features/training/lib/workspaceFiles";

export interface WorkspaceEditorHandle { saveAll: () => Promise<number> }
interface Props {
  workspace: TrainingWorkspace; entries: WorkspaceEntry[]; runId?: string; entryPoint: string;
  readOnly: boolean; onRefresh: () => Promise<TrainingWorkspace>; onDirty: (dirty: boolean) => void;
  externallyBusy?: boolean;
  onBusy: (busy: boolean) => void;
}
export const WorkspaceEditor = forwardRef<WorkspaceEditorHandle, Props>(function WorkspaceEditor({ workspace, entries, runId, entryPoint, readOnly, externallyBusy = false, onRefresh, onDirty, onBusy }, ref) {
  const { t } = useTranslation("training");
  const [selected, setSelected] = useState<string | null>(null);
  const [contents, setContents] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState<Record<string, string>>({});
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const workspaceRef = useRef(workspace); workspaceRef.current = workspace;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [localBusy, setBusy] = useState(false);
  const busy = localBusy || externallyBusy;
  const [dialog, setDialog] = useState<"new" | "edit" | "folder" | "move" | null>(null);
  const [pathValue, setPathValue] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [reloadOpen, setReloadOpen] = useState(false);
  const needsReload = useRef(false);
  const [preview, setPreview] = useState(false);
  const file = entries.find((entry) => entry.path === selected);
  const parent = file?.kind === "folder" ? file.path : selected?.includes("/") ? selected.slice(0, selected.lastIndexOf("/")) : "";
  const nodes = useMemo(() => workspaceTree(entries), [entries]);
  const scope = runId ?? workspace.id;
  const loadedScope = useRef(scope);
  const currentScope = useRef(scope); currentScope.current = scope;
  const key = (path: string) => `${scope}:${path}`;
  const selectedText = selected ? dirty[selected] ?? contents[key(selected)] ?? "" : "";

  useEffect(() => { onDirty(Object.keys(dirty).length > 0); }, [dirty, onDirty]);
  useEffect(() => {
    if (!file || file.kind === "folder" || contents[`${scope}:${file.path}`] !== undefined) return;
    let alive = true;
    const requestedScope = scope;
    void (runId ? getRunFile(runId, file.path) : readEntry(file)).then((content) => {
      if (alive && currentScope.current === requestedScope) setContents((current) => ({ ...current, [`${scope}:${file.path}`]: content }));
    }).catch((error) => { if (alive) toast.error(getApiErrorMessage(error, t("studio.failed"))); });
    return () => { alive = false; };
  // Entries contain short-lived signed URLs and must remain dependencies.
  }, [file, runId, scope, contents, t]);

  async function refresh() { const next = await onRefresh(); workspaceRef.current = next; return next; }
  async function saveAll() {
    if (needsReload.current) throw new Error(t("studio.reload"));
    if (readOnly && Object.keys(dirtyRef.current).length) throw new Error(t("studio.locked"));
    let revision = workspaceRef.current.revision;
    for (const [path, content] of Object.entries(dirtyRef.current)) {
      const entry = workspaceRef.current.entries.find((item) => item.path === path);
      if (!entry || entry.kind === "folder") throw new Error(t("studio.reload"));
      let result;
      try { result = await saveWorkspaceEntry(workspace.id, revision, { path, kind: entry.kind, file: null }, entry.id, content); }
      catch (error) { needsReload.current = true; throw error; }
      revision = result.revision;
      workspaceRef.current = { ...workspaceRef.current, revision };
      setContents((current) => ({ ...current, [key(path)]: content }));
      setDirty((current) => { const next = { ...current }; delete next[path]; return next; });
      const remaining = { ...dirtyRef.current }; delete remaining[path]; dirtyRef.current = remaining;
    }
    if (revision !== workspace.revision) await refresh();
    return revision;
  }
  useImperativeHandle(ref, () => ({ saveAll }));

  async function task(action: () => Promise<void>) {
    if (busy || externallyBusy) return;
    setBusy(true); onBusy(true);
    try { await action(); }
    catch (error) { needsReload.current = true; toast.error(getApiErrorMessage(error, t("studio.failed"))); }
    finally { setBusy(false); onBusy(false); }
  }
  async function cleanDraft() { await saveAll(); return workspaceRef.current; }
  async function saveSelection(selection: TrainingFileSelection) {
    await task(async () => {
      const current = await cleanDraft();
      await saveWorkspaceEntry(workspace.id, current.revision, selection, dialog === "edit" ? file?.id : undefined);
      setDialog(null); setSelected(selection.path);
      setContents({}); await refresh();
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
      await saveWorkspaceEntry(workspace.id, current.revision, { path: destination, kind: entry.kind, file: null }, entry.id);
      setSelected(destination); setDialog(null); setContents({}); await refresh();
    });
  }
  function drop(event: DragEvent, folder: string) {
    if (readOnly || busy) return;
    const internal = event.dataTransfer.getData("application/x-training-path");
    if (internal) { void move(internal, folder); return; }
    // Read browser drag handles before awaiting network requests.
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
        const result = await saveWorkspaceEntry(workspace.id, current.revision, item.file ? { path, kind: kindForPath(path), file: item.file } : { path, kind: "folder", file: null });
        current = { ...current, revision: result.revision }; workspaceRef.current = current; known.add(path);
      }
      await refresh();
    });
  }
  async function download() {
    if (runId) { window.open(await downloadRunInput(runId), "_blank", "noopener,noreferrer"); return; }
    const current = await cleanDraft();
    const freshFile = current.entries.find((entry) => entry.path === selected);
    if (freshFile?.kind !== "folder" && freshFile?.download_url) { window.open(freshFile.download_url, "_blank", "noopener,noreferrer"); return; }
    const bundle: Zippable = {};
    for (const entry of current.entries) {
      if (selected && !entry.path.startsWith(selected + "/")) continue;
      bundle[entry.path + (entry.kind === "folder" ? "/" : "")] = entry.kind === "folder" ? new Uint8Array() : strToU8(await readEntry(entry));
    }
    const blob = new Blob([zipSync(bundle).slice().buffer], { type: "application/zip" });
    const href = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = href; link.download = "input.zip"; link.click(); setTimeout(() => URL.revokeObjectURL(href), 1000);
  }

  // Scope changes are driven by the explicit run selector. The parent prevents
  // leaving the draft while it contains unsaved edits.
  if (loadedScope.current !== scope) loadedScope.current = scope;
  return <div className="rounded-surface border border-border bg-surface overflow-hidden">
    <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
      <span className="mr-auto text-style-body-strong">{t("studio.input")}{runId ? ` · ${t("studio.snapshot")}` : ""}</span>
      <Button size="sm" variant="secondary" icon={<FilePlus className="h-4 w-4" />} disabled={readOnly || busy} onClick={() => setDialog("new")}>{t("workspace.fileDialog.create")}</Button>
      <Button size="sm" variant="secondary" icon={<FolderPlus className="h-4 w-4" />} disabled={readOnly || busy} onClick={() => { setPathValue(parent ? parent + "/" : ""); setDialog("folder"); }}>{t("studio.newFolder")}</Button>
      <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} disabled={busy} onClick={() => void task(download)}>{t("studio.download")}</Button>
      <Button size="sm" variant="secondary" icon={<Move className="h-4 w-4" />} disabled={readOnly || busy || !file || file.path === "requirements.txt"} onClick={() => { setPathValue(""); setDialog("move"); }}>{t("studio.move")}</Button>
      <Button size="sm" variant="secondary" icon={<Trash2 className="h-4 w-4" />} disabled={readOnly || busy || !file} onClick={() => setDeleting(true)}>{t("studio.delete")}</Button>
      <Button size="sm" icon={<Save className="h-4 w-4" />} disabled={readOnly || busy || !Object.keys(dirty).length} onClick={() => void task(async () => { await saveAll(); })}>{t("studio.save")}</Button>
      {!readOnly && <Button size="sm" variant="secondary" disabled={busy} onClick={() => setReloadOpen(true)}>{t("studio.reload")}</Button>}
    </div>
    <div className="grid min-h-96 md:grid-cols-[16rem_minmax(0,1fr)]">
      <div className="border-r border-border p-2" onDragOver={!readOnly ? (event) => event.preventDefault() : undefined} onDrop={!readOnly ? (event) => { event.preventDefault(); drop(event, ""); } : undefined}>
        <button type="button" className="p-2 text-style-caption text-color-muted-foreground" onClick={() => setSelected(null)}>{t("studio.input")}</button>
        <DirectoryTree nodes={nodes} selectedPath={selected} onSelect={setSelected} unsavedContents={dirty} currentEntryPoint={entryPoint}
          expandedFolders={expanded} toggleFolder={(path) => setExpanded((current) => { const next = new Set(current); if (next.has(path)) next.delete(path); else next.add(path); return next; })}
          onEditFile={!readOnly && !busy ? (path) => { setSelected(path); setDialog("edit"); } : undefined}
          onMove={!readOnly && !busy ? (path, folder) => void move(path, folder) : undefined} onDropFiles={!readOnly && !busy ? drop : undefined} />
      </div>
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-2 border-b border-border p-2 text-style-caption">
          <span>{selected ?? t("studio.selectFile")}</span>
          {file?.kind === "script" && <Button size="sm" variant="secondary" icon={<Play className="h-3 w-3" />} disabled={readOnly || busy || entryPoint === file.path} onClick={() => void task(async () => { const current = await cleanDraft(); await updateWorkspace(workspace.id, current.revision, { entry_point: file.path }); await refresh(); })}>{t("studio.entryPoint")}</Button>}
          {file?.kind === "document" && <Button size="sm" variant="secondary" onClick={() => setPreview(!preview)}>{t(preview ? "studio.editor" : "studio.preview")}</Button>}
        </div>
        {file && file.kind !== "folder" ? file.kind === "data" ? <DataViewer key={key(file.path)} initialCsvText={selectedText} readOnly /> : preview && file.kind === "document" ? <MarkdownPreview content={selectedText} /> :
          <CodeViewer height="430px" path={key(file.path)} language={file.kind === "script" ? "python" : file.kind === "config" ? "json" : file.kind === "document" ? "markdown" : "plaintext"} value={selectedText}
            options={{ readOnly: readOnly || busy || contents[key(file.path)] === undefined, minimap: { enabled: false }, automaticLayout: true }}
            onChange={(value) => { if (!readOnly && file) setDirty((current) => ({ ...current, [file.path]: value ?? "" })); }} /> : <p className="p-6 text-style-body text-color-muted-foreground">{t("studio.selectFile")}</p>}
      </div>
    </div>
    {(dialog === "new" || (dialog === "edit" && file && file.kind !== "folder")) && <TrainingFileDialog key={`${dialog}:${selected}`} existing={dialog === "edit" && file && file.kind !== "folder" ? { path: file.path, kind: file.kind } : undefined} parentPath={parent} hasRequirements={entries.some((entry) => entry.path === "requirements.txt")} saving={busy} onClose={() => setDialog(null)} onSave={(selection) => void saveSelection(selection)} />}
    {(dialog === "folder" || dialog === "move") && <BaseDialog title={t(dialog === "folder" ? "studio.newFolder" : "studio.move")} onClose={() => setDialog(null)}>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (dialog === "move" && selected) void move(selected, pathValue.trim()); else void task(async () => { const current = await cleanDraft(); await saveWorkspaceEntry(workspace.id, current.revision, { path: pathValue.trim(), kind: "folder", file: null }); setDialog(null); await refresh(); }); }}>
        <Input label={t(dialog === "folder" ? "studio.folderPath" : "studio.destination")} value={pathValue} onChange={(event) => setPathValue(event.target.value)} />
        <Button type="submit" disabled={busy}>{t("studio.save")}</Button>
      </form>
    </BaseDialog>}
    <ConfirmDialog open={deleting} title={t("studio.delete")} description={t("studio.deleteConfirm")} confirmText={t("studio.delete")} tone="danger" onCancel={() => setDeleting(false)} onConfirm={() => void task(async () => { const current = await cleanDraft(); if (file) await deleteWorkspaceEntry(workspace.id, file.id, current.revision); setDeleting(false); setSelected(null); setContents({}); await refresh(); })} />
    <ConfirmDialog open={reloadOpen} title={t("studio.unsaved")} description={t("studio.discard")} confirmText={t("studio.reload")} tone="danger" onCancel={() => setReloadOpen(false)} onConfirm={() => void task(async () => { await refresh(); setDirty({}); dirtyRef.current = {}; setContents({}); needsReload.current = false; setReloadOpen(false); })} />
  </div>;
});

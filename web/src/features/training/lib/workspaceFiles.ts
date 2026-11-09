import type { DragEvent } from "react";
import type { WorkspaceEntry } from "@/features/training/api/workspacesApi";
import type { TrainingFileKind } from "@/features/training/components/TrainingFileDialog";
import type { SourceTreeNode } from "@/shared/types/sourceTreeModel";

export function workspaceTree(entries: WorkspaceEntry[]): SourceTreeNode[] {
  const root: SourceTreeNode = { name: "", path: "", type: "folder", children: [] };
  for (const entry of entries) {
    let parent = root;
    entry.path.split("/").forEach((part, index, parts) => {
      const path = parts.slice(0, index + 1).join("/");
      let node = parent.children.find((item) => item.path === path);
      if (!node) {
        node = { name: part, path, type: index < parts.length - 1 || entry.kind === "folder" ? "folder" : "file", children: [] };
        parent.children.push(node);
      }
      parent = node;
    });
  }
  const sort = (nodes: SourceTreeNode[]) => { nodes.sort((a, b) => a.type === b.type ? a.name.localeCompare(b.name) : a.type === "folder" ? -1 : 1); nodes.forEach((node) => sort(node.children)); };
  sort(root.children);
  return root.children;
}
export function kindForPath(path: string): TrainingFileKind {
  if (path === "requirements.txt") return "requirements";
  if (path.endsWith(".py")) return "script";
  if (path.endsWith(".csv")) return "data";
  if (path.endsWith(".json")) return "config";
  if (path.endsWith(".md")) return "document";
  throw new Error("Unsupported file type.");
}

export async function droppedEntries(event: DragEvent): Promise<{ path: string; file: File | null }[]> {
  const roots = Array.from(event.dataTransfer.items).map((item) => item.webkitGetAsEntry?.()).filter((entry): entry is FileSystemEntry => Boolean(entry));
  if (!roots.length) return Array.from(event.dataTransfer.files).map((file) => ({ path: file.name, file }));
  const result: { path: string; file: File | null }[] = [];
  async function visit(entry: FileSystemEntry, parent: string) {
    const path = parent + entry.name;
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      result.push({ path, file });
    } else {
      result.push({ path, file: null });
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      let children: FileSystemEntry[];
      do {
        children = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
        for (const child of children) await visit(child, path + "/");
      } while (children.length);
    }
  }
  for (const entry of roots) await visit(entry, "");
  return result;
}

import { useMemo } from "react";
import { FileCode2, Boxes } from "lucide-react";

interface TreeNode {
  name: string;
  isDirectory: boolean;
  children: Record<string, TreeNode>;
}

interface TreeLine {
  text: string;
  isDirectory: boolean;
  name: string;
}

function buildTree(paths: string[]): TreeNode {
  const root: TreeNode = { name: "root", isDirectory: true, children: {} };

  for (const path of paths) {
    const isDir = path.endsWith("/");
    const parts = path.split("/").filter(Boolean);
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;

      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          isDirectory: isLast ? isDir : true,
          children: {},
        };
      }
      current = current.children[part];
    }
  }

  return root;
}

function generateTreeLines(node: TreeNode, prefix: string = ""): TreeLine[] {
  const lines: TreeLine[] = [];
  const keys = Object.keys(node.children).sort((a, b) => {
    const aIsD = node.children[a].isDirectory;
    const bIsD = node.children[b].isDirectory;
    if (aIsD && !bIsD) return -1;
    if (!aIsD && bIsD) return 1;
    return a.localeCompare(b);
  });

  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const child = node.children[key];
    const isLast = i === keys.length - 1;

    const connector = isLast ? "└── " : "├── ";
    const childPrefix = isLast ? "    " : "│   ";

    lines.push({
      text: prefix + connector + child.name + (child.isDirectory ? "/" : ""),
      isDirectory: child.isDirectory,
      name: child.name,
    });

    lines.push(...generateTreeLines(child, prefix + childPrefix));
  }

  return lines;
}

export function PackagePreview({
  preview,
  compact = false,
}: {
  preview: string[];
  compact?: boolean;
}) {
  const lines = useMemo(() => {
    if (!preview || preview.length === 0) return [];

    const root = buildTree(preview);
    const rootKeys = Object.keys(root.children);

    const result: TreeLine[] = [];
    if (rootKeys.length === 1) {
      const topNode = root.children[rootKeys[0]];
      result.push({
        text: topNode.name + "/",
        isDirectory: true,
        name: topNode.name,
      });
      result.push(...generateTreeLines(topNode, ""));
    } else {
      result.push(...generateTreeLines(root, ""));
    }
    return result;
  }, [preview]);

  return (
    <div
      className={`rounded-surface border border-terminal-border bg-terminal p-4 font-mono text-style-code-sm text-color-terminal-foreground ${compact ? "max-h-60 overflow-auto custom-scrollbar" : ""}`}
    >
      {lines.map((line, idx) => {
        // Extract the connector/prefix part vs the actual file name
        const nameIndex = line.text.lastIndexOf(line.name);
        const prefix = line.text.substring(0, nameIndex);
        const suffix = line.text.substring(nameIndex + line.name.length);

        return (
          <div key={idx} className="flex items-center whitespace-pre py-1">
            <span className="text-color-terminal-muted">{prefix}</span>
            <span
              className={`flex items-center gap-1.5 ${line.isDirectory ? "text-color-terminal-info font-semibold" : "text-color-terminal-muted"}`}
            >
              {line.isDirectory ? (
                <Boxes className="h-3 w-3" />
              ) : (
                <FileCode2 className="h-3 w-3 opacity-60" />
              )}
              {line.name}
              {suffix}
            </span>
          </div>
        );
      })}
    </div>
  );
}

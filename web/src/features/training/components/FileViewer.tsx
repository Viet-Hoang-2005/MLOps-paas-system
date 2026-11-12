import { getFileLanguage } from "@/features/training/lib/workspaceFiles";
import { useTheme } from "@/app/theme/useTheme";
import { CodeViewer } from "@/shared/components/CodeViewer";
import { DataViewer } from "@/shared/components/DataViewer";
import { MarkdownPreview } from "./MarkdownPreview";

export interface FileViewerProps {
  path: string;
  content: string;
  readOnly?: boolean;
  showMarkdownPreview?: boolean;
  onChange?: (value: string) => void;
  className?: string;
}

export function FileViewer({
  path,
  content,
  readOnly = false,
  showMarkdownPreview = false,
  onChange,
  className,
}: FileViewerProps) {
  const { resolvedTheme } = useTheme();
  const lower = path.toLowerCase();

  if (/\.(png|jpe?g)$/i.test(path)) return <img src={content || undefined} alt={path} className="max-h-full max-w-full object-contain" />;
  if (lower.endsWith(".csv")) {
    return (
      <div className={className || "h-full w-full flex-1 overflow-auto"}>
        <DataViewer
          initialCsvText={content}
          onChange={onChange}
          readOnly={readOnly}
        />
      </div>
    );
  }

  if (lower.endsWith(".md") && showMarkdownPreview) {
    return (
      <div className={className || "h-full w-full flex-1 overflow-auto p-4"}>
        <MarkdownPreview content={content} />
      </div>
    );
  }

  return (
    <div className={className || "h-full w-full flex-1 min-h-100"}>
      <CodeViewer
        height="100%"
        path={path}
        language={getFileLanguage(path)}
        theme={resolvedTheme === "dark" ? "vs-dark" : "vs"}
        value={content}
        onChange={onChange ? (val) => onChange(val ?? "") : undefined}
        options={{
          readOnly,
          minimap: { enabled: false },
          wordWrap: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
        }}
      />
    </div>
  );
}

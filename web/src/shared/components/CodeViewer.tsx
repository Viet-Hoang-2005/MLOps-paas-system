import { lazy, Suspense, type ReactNode } from "react";
import type { EditorProps } from "@monaco-editor/react";
import { FileCode } from "lucide-react";
import { Skeleton } from "./Skeleton";
import type { ButtonProps } from "@/shared/components/Button";
import { Button } from "@/shared/components/Button";
import { cn } from "@/shared/lib/cn";

const MonacoEditor = lazy(() =>
  import("@monaco-editor/react").then((module) => ({ default: module.Editor })),
);

export interface CodeViewerActionItem {
  label: ReactNode;
  icon?: ReactNode;
  variant?: ButtonProps["variant"];
  disabled?: boolean;
  loading?: boolean;
  title?: string;
  className?: string;
  onClick?: () => void;
}

export interface CodeViewerProps extends EditorProps {
  title?: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
  actions?: ReactNode;
  actionButtons?: readonly CodeViewerActionItem[];
  containerClassName?: string;
  headerClassName?: string;
}

export function CodeViewer({
  title,
  icon,
  badge,
  actions,
  actionButtons,
  containerClassName,
  headerClassName,
  height,
  ...editorProps
}: CodeViewerProps) {
  const content = (
    <Suspense
      fallback={
        <div className="space-y-3 p-4">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-64 w-full" />
        </div>
      }
    >
      <MonacoEditor
        height={height ?? (title ? "100%" : undefined)}
        {...editorProps}
      />
    </Suspense>
  );

  if (!title) {
    return content;
  }

  return (
    <div
      className={cn(
        "flex flex-col h-full w-full min-h-0 rounded-surface border border-border bg-surface overflow-hidden",
        containerClassName,
      )}
    >
      <div
        className={cn(
          "flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface-muted px-4 py-2.5 shrink-0",
          headerClassName,
        )}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {icon ?? <FileCode className="h-4 w-4 text-color-primary shrink-0" />}
          {typeof title === "string" ? (
            <span className="truncate font-mono text-style-body font-semibold text-color-foreground">
              {title}
            </span>
          ) : (
            title
          )}
          {badge}
        </div>
        {(actions || (actionButtons && actionButtons.length > 0)) && (
          <div className="flex items-center gap-2 shrink-0">
            {actions}
            {actionButtons?.map((btn, index) => (
              <Button
                key={index}
                variant={btn.variant ?? "secondary"}
                size="sm"
                icon={btn.icon}
                loading={btn.loading}
                disabled={btn.disabled}
                title={btn.title}
                className={btn.className}
                onClick={btn.onClick}
              >
                {btn.label}
              </Button>
            ))}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0">{content}</div>
    </div>
  );
}

export default CodeViewer;

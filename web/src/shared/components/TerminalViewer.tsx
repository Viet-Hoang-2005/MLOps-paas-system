import Anser from "anser";
import { Clipboard, Loader2, Terminal } from "lucide-react";
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/cn";
import { terminalLines } from "@/shared/lib/terminalLines";
import { toast } from "@/shared/lib/toastStore";

function formatAnsiColor(color: string | null | undefined): string | undefined {
  if (!color) return undefined;
  const trimmed = color.trim();
  if (
    trimmed.startsWith("#") ||
    // color-ignore: ANSI escape sequence decoding for terminal stream.
    trimmed.startsWith("rgb(") ||
    // color-ignore: ANSI escape sequence decoding for terminal stream.
    trimmed.startsWith("rgba(") ||
    trimmed.startsWith("var(")
  ) {
    return trimmed;
  }
  // color-ignore: ANSI escape sequence decoding for terminal stream.
  return `rgb(${trimmed})`;
}

function getAnsiStyle(
  segment: Anser.AnserJsonEntry,
  overrideFgColor?: string | null,
): CSSProperties {
  const decorations = new Set(segment.decorations);
  const textDecorations = [
    decorations.has("underline") ? "underline" : "",
    decorations.has("strikethrough") ? "line-through" : "",
  ].filter(Boolean);

  const fgColor =
    overrideFgColor !== undefined
      ? (overrideFgColor ?? undefined)
      : segment.fg_truecolor
        ? formatAnsiColor(segment.fg_truecolor)
        : segment.fg
          ? formatAnsiColor(segment.fg)
          : undefined;

  const bgColor = segment.bg_truecolor
    ? formatAnsiColor(segment.bg_truecolor)
    : segment.bg
      ? formatAnsiColor(segment.bg)
      : undefined;

  return {
    color: fgColor,
    backgroundColor: bgColor,
    // typography-ignore: ANSI decorations are runtime data, not application typography.
    fontWeight: decorations.has("bold") ? 700 : undefined,
    fontStyle: decorations.has("italic") ? "italic" : undefined,
    opacity: overrideFgColor !== undefined ? undefined : decorations.has("dim") ? 0.7 : undefined,
    visibility: decorations.has("hidden") ? "hidden" : undefined,
    textDecoration: textDecorations.length
      ? textDecorations.join(" ")
      : undefined,
  };
}

const isPipProgressBarLine = (log: string): boolean =>
  /[━╺╸]/.test(log) ||
  (/[\d.]+\s*(?:kB|MB|GB|B)\b/i.test(log) && /[━─█]/.test(log));

interface ParsedLogSegment {
  content: string;
  type: "normal" | "completed" | "track";
  segment: Anser.AnserJsonEntry;
}

function parseLogSegments(log: string): ParsedLogSegment[] {
  const isProgress = isPipProgressBarLine(log);
  const rawSegments = Anser.ansiToJson(log, { remove_empty: true });

  if (!isProgress) {
    return rawSegments.map((segment) => ({
      content: segment.content,
      type: "normal",
      segment,
    }));
  }

  const result: ParsedLogSegment[] = [];
  let hasCompletedBar = false;

  for (const segment of rawSegments) {
    const text = segment.content;

    // Split compound text containing both completed and track characters
    if (/[━█]/.test(text) && /╺|[─░]/.test(text)) {
      const match = text.match(/^(\s*)(?:([━█]+╸?))?(?:(╺[━─]*|[─░]+))?(.*)$/);
      if (match && (match[2] || match[3])) {
        if (match[1]) {
          result.push({ content: match[1], type: "normal", segment });
        }
        if (match[2]) {
          result.push({ content: match[2], type: "completed", segment });
          hasCompletedBar = true;
        }
        if (match[3]) {
          result.push({ content: match[3], type: "track", segment });
        }
        if (match[4]) {
          result.push({ content: match[4], type: "normal", segment });
        }
        continue;
      }
    }

    if (/^[━█╸]+$/.test(text) && !hasCompletedBar) {
      result.push({ content: text, type: "completed", segment });
      hasCompletedBar = true;
    } else if (
      /^╺[━─]*$/.test(text) ||
      (hasCompletedBar && /^[━─░]+$/.test(text))
    ) {
      result.push({ content: text, type: "track", segment });
    } else if (hasCompletedBar && /^[━─█╺╸]+$/.test(text)) {
      result.push({ content: text, type: "track", segment });
    } else {
      const match = text.match(/^(\s*)(?:([━█]+╸?))?(?:(╺[━─]*|[─░]+))?(.*)$/);
      if (match && (match[2] || match[3])) {
        if (match[1]) {
          result.push({ content: match[1], type: "normal", segment });
        }
        if (match[2]) {
          result.push({ content: match[2], type: "completed", segment });
          hasCompletedBar = true;
        }
        if (match[3]) {
          result.push({ content: match[3], type: "track", segment });
        }
        if (match[4]) {
          result.push({ content: match[4], type: "normal", segment });
        }
      } else {
        result.push({ content: text, type: "normal", segment });
      }
    }
  }

  return result;
}

function AnsiLogLine({ log }: { log: string }) {
  const parsedSegments = parseLogSegments(log);

  return parsedSegments.map(({ content, type, segment }, index) => {
    if (type === "completed") {
      return (
        <span
          key={`${index}-${content}`}
          className="text-color-terminal-foreground"
          style={getAnsiStyle(segment, null)}
        >
          {content}
        </span>
      );
    }

    if (type === "track") {
      return (
        <span
          key={`${index}-${content}`}
          className="text-color-terminal-muted"
          style={getAnsiStyle(segment, null)}
        >
          {content}
        </span>
      );
    }

    return (
      <span key={`${index}-${content}`} style={getAnsiStyle(segment)}>
        {content}
      </span>
    );
  });
}

export type TerminalButtonType =
  "primary" | "secondary" | "info" | "success" | "warning" | "danger";

export type TerminalActionTone =
  "default" | "start" | "warning" | "danger" | "success";

const toneToVariantMap: Record<TerminalActionTone, TerminalButtonType> = {
  default: "secondary",
  start: "primary",
  success: "success",
  warning: "warning",
  danger: "danger",
};

const terminalButtonVariants: Record<TerminalButtonType, string> = {
  secondary:
    "border-border bg-surface text-color-foreground shadow-sm hover:border-border-strong hover:bg-surface-hover active:bg-surface-active",
  primary:
    "border-primary bg-surface text-color-primary shadow-sm hover:border-primary-hover hover:bg-surface-hover active:bg-surface-active",
  info: "border-info bg-surface text-color-info shadow-sm hover:border-info-hover hover:bg-surface-hover active:bg-surface-active",
  success:
    "border-success bg-surface text-color-success shadow-sm hover:border-success-hover hover:bg-surface-hover active:bg-surface-active",
  warning:
    "border-warning bg-surface text-color-warning shadow-sm hover:border-warning-hover hover:bg-surface-hover active:bg-surface-active",
  danger:
    "border-danger bg-surface text-color-danger shadow-sm hover:border-danger-hover hover:bg-surface-hover active:bg-surface-active",
};

function isTerminalButtonType(value: unknown): value is TerminalButtonType {
  return (
    typeof value === "string" &&
    ["primary", "secondary", "info", "success", "warning", "danger"].includes(
      value,
    )
  );
}

export interface TerminalButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "type"
> {
  type?: TerminalButtonType | "button" | "submit" | "reset";
  variant?: TerminalButtonType;
  tone?: TerminalActionTone;
  loading?: boolean;
  icon?: ReactNode;
}

export function TerminalButton({
  type = "button",
  variant,
  tone,
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...props
}: TerminalButtonProps) {
  const resolvedVariant: TerminalButtonType =
    variant ??
    (isTerminalButtonType(type)
      ? type
      : tone
        ? toneToVariantMap[tone]
        : "secondary");

  const buttonHtmlType = isTerminalButtonType(type) ? "button" : type;

  return (
    <button
      type={buttonHtmlType}
      disabled={disabled || loading}
      className={cn(
        "inline-flex h-8 select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-surface border px-3 text-style-caption-strong shadow-sm transition-[background-color,border-color,color,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-disabled disabled:text-color-foreground-disabled",
        terminalButtonVariants[resolvedVariant],
        className,
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
      ) : icon ? (
        <span className="shrink-0">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}

export type TerminalActionButtonProps = TerminalButtonProps;
export const TerminalActionButton = TerminalButton;

export interface TerminalActionItem {
  label: ReactNode;
  icon?: ReactNode;
  type?: TerminalButtonType | "button" | "submit" | "reset";
  variant?: TerminalButtonType;
  tone?: TerminalActionTone;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
  className?: string;
  onClick?: () => void;
}

export interface TerminalViewerProps {
  title?: ReactNode;
  badge?: ReactNode;
  logs?: readonly string[];
  placeholder?: ReactNode;
  actions?: ReactNode;
  actionButtons?: readonly TerminalActionItem[];
  className?: string;
  bodyClassName?: string;
}

export function TerminalViewer({
  title,
  badge,
  logs = [],
  placeholder,
  actions,
  actionButtons,
  className,
  bodyClassName,
}: TerminalViewerProps) {
  const { t } = useTranslation("common");
  const terminalRef = useRef<HTMLDivElement>(null);
  const displayLogs = useMemo(() => terminalLines(logs), [logs]);
  const previousLogs = useRef<readonly string[]>([]);

  useEffect(() => {
    const previous = previousLogs.current;
    const changed =
      displayLogs.length !== previous.length ||
      displayLogs.some((line, index) => line !== previous[index]);
    previousLogs.current = displayLogs;
    if (
      changed &&
      displayLogs.length > 0 &&
      displayLogs.length >= previous.length &&
      terminalRef.current
    ) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [displayLogs]);

  const copyLogs = async () => {
    await navigator.clipboard.writeText(displayLogs.join("\n"));
    toast.success(t("terminal.copied"));
  };

  return (
    <div
      className={cn(
        "overflow-hidden rounded-surface border border-terminal-border bg-terminal shadow-lg",
        className,
      )}
    >
      <div className="flex min-h-13 shrink-0 items-center border-b border-terminal-border bg-terminal-header px-4 py-3">
        <Terminal className="mr-2 h-4 w-4 shrink-0 text-color-terminal-muted" />
        <span className="truncate font-mono text-style-code-lg text-color-terminal-foreground">
          {title ?? t("terminal.title")}
        </span>
        {badge && <div className="ml-2.5 flex items-center">{badge}</div>}
        <div className="ml-auto flex items-center gap-2">
          {actions}
          {actionButtons?.map((btn, index) => (
            <TerminalButton
              key={index}
              type={btn.type}
              variant={btn.variant}
              tone={btn.tone}
              icon={btn.icon}
              loading={btn.loading}
              disabled={btn.disabled}
              title={btn.title}
              className={btn.className}
              onClick={btn.onClick}
            >
              {btn.label}
            </TerminalButton>
          ))}
          <TerminalButton
            variant="secondary"
            onClick={() => void copyLogs()}
            title={t("terminal.copyTitle")}
            icon={<Clipboard className="h-4 w-4" />}
          >
            {t("terminal.copy")}
          </TerminalButton>
        </div>
      </div>
      <div
        ref={terminalRef}
        className={cn(
          "custom-scrollbar h-72 w-full overflow-y-auto bg-terminal p-4 font-mono text-style-terminal text-color-terminal-foreground antialiased",
          bodyClassName,
        )}
        style={{ scrollBehavior: "smooth" }}
      >
        {displayLogs.length > 0 ? (
          displayLogs.map((log, index) => (
            <div
              key={`${index}-${log}`}
              className="mb-1 break-all whitespace-pre-wrap"
            >
              <AnsiLogLine log={log} />
            </div>
          ))
        ) : placeholder ? (
          <div className="break-all whitespace-pre-wrap text-color-terminal-muted italic">
            {placeholder}
          </div>
        ) : null}
      </div>
    </div>
  );
}

TerminalViewer.Button = TerminalButton;
TerminalViewer.ActionButton = TerminalActionButton;

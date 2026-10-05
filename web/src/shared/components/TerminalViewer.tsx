import Anser from "anser";
import { Clipboard, Loader2, Terminal } from "lucide-react";
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/cn";
import { toast } from "@/shared/types/toastStore";

function getAnsiStyle(segment: Anser.AnserJsonEntry): CSSProperties {
  const decorations = new Set(segment.decorations);
  const textDecorations = [
    decorations.has("underline") ? "underline" : "",
    decorations.has("strikethrough") ? "line-through" : "",
  ].filter(Boolean);

  return {
    color: segment.fg_truecolor || segment.fg || undefined,
    backgroundColor: segment.bg_truecolor || segment.bg || undefined,
    // typography-ignore: ANSI decorations are runtime data, not application typography.
    fontWeight: decorations.has("bold") ? 700 : undefined,
    fontStyle: decorations.has("italic") ? "italic" : undefined,
    opacity: decorations.has("dim") ? 0.7 : undefined,
    visibility: decorations.has("hidden") ? "hidden" : undefined,
    textDecoration: textDecorations.length
      ? textDecorations.join(" ")
      : undefined,
  };
}

function AnsiLogLine({ log }: { log: string }) {
  return Anser.ansiToJson(log, { remove_empty: true }).map((segment, index) => (
    <span key={`${index}-${segment.content}`} style={getAnsiStyle(segment)}>
      {segment.content}
    </span>
  ));
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

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  const copyLogs = async () => {
    await navigator.clipboard.writeText(logs.join("\n"));
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
        {logs.length > 0 ? (
          logs.map((log, index) => (
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

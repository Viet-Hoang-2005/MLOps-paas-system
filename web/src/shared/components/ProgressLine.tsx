import type { ElementType } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/shared/lib/cn";

export type ProgressLineState =
  | "pending"
  | "active"
  | "completed"
  | "failed"
  | "cancelled"
  | "skipped";

export interface ProgressLineStep {
  id: string;
  label: string;
  state: ProgressLineState;
  icon: ElementType;
  timestamp?: string;
  helper?: string;
}

const stepTone: Record<ProgressLineState, string> = {
  pending: "border-border bg-surface text-color-muted-foreground",
  active: "border-primary bg-primary/10 text-color-primary ring-4 ring-primary/10",
  completed: "border-success bg-success/10 text-color-success",
  failed: "border-danger bg-danger-subtle text-color-danger ring-4 ring-danger/10",
  cancelled: "border-warning bg-warning/10 text-color-warning ring-4 ring-warning/10",
  skipped: "border-border bg-muted text-color-muted-foreground opacity-60",
};

export interface ProgressLineProps {
  steps: ProgressLineStep[];
  className?: string;
}

export function ProgressLine({ steps, className }: ProgressLineProps) {
  const { t } = useTranslation("common");

  return (
    <ol
      className={cn("flex min-w-150 w-full items-start justify-between", className)}
      aria-label={t("steps.progressLabel")}
    >
      {steps.map((step, index) => {
        const Icon = step.icon;
        const isLast = index === steps.length - 1;
        const finished = step.state === "completed";
        return (
          <li
            key={step.id}
            className={`relative flex ${isLast ? "flex-none" : "flex-1"} flex-col`}
            aria-current={step.state === "active" ? "step" : undefined}
          >
            <div className="flex w-full items-center">
              <span
                className={`relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 transition-all ${stepTone[step.state]}`}
              >
                <Icon
                  className={
                    step.state === "active"
                      ? "h-5 w-5 animate-pulse"
                      : "h-5 w-5"
                  }
                />
              </span>
              {!isLast && (
                <span
                  className={`mx-2 h-1 flex-1 rounded-full ${finished ? "bg-success" : "bg-border"}`}
                />
              )}
            </div>
            <div className="mt-4 w-36 pr-4">
              <span className="text-style-body-strong text-color-foreground">
                {step.label}
              </span>
              {step.timestamp && (
                <span className="mt-1 block text-style-caption text-color-muted-foreground">
                  {step.timestamp}
                </span>
              )}
              {step.helper && (
                <span className="mt-1 block text-style-caption text-color-muted-foreground">
                  {step.helper}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

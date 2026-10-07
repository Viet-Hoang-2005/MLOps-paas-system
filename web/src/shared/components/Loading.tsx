import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/shared/lib/cn";

export type LoadingVariant = "spinner" | "progress";
export type LoadingSize = "sm" | "md" | "lg" | "xl";

export interface LoadingProps {
  variant?: LoadingVariant;
  size?: LoadingSize;
  text?: string;
  description?: string;
  value?: number;
  max?: number;
  indeterminate?: boolean;
  showPercent?: boolean;
  formatValue?: (value: number, max: number, percentage: number) => string;
  icon?: ReactNode;
  className?: string;
  spinnerClassName?: string;
  trackClassName?: string;
  indicatorClassName?: string;
}

const spinnerSizeClasses: Record<LoadingSize, string> = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
  xl: "h-12 w-12",
};

const spinnerTitleClasses: Record<LoadingSize, string> = {
  sm: "text-style-caption",
  md: "text-style-body",
  lg: "text-style-body-strong",
  xl: "text-style-page-title font-semibold",
};

const progressTrackClasses: Record<LoadingSize, string> = {
  sm: "h-1.5",
  md: "h-2.5",
  lg: "h-3.5",
  xl: "h-5",
};

export function Loading({
  variant = "spinner",
  size = "md",
  text,
  description,
  value,
  max = 100,
  indeterminate,
  showPercent,
  formatValue,
  icon,
  className,
  spinnerClassName,
  trackClassName,
  indicatorClassName,
}: LoadingProps) {
  const { t } = useTranslation("common");

  if (variant === "progress") {
    const isIndeterminate = indeterminate ?? value === undefined;
    const clampedValue = Math.max(0, Math.min(value ?? 0, max));
    const percentage = max > 0 ? Math.round((clampedValue / max) * 100) : 0;
    const shouldShowPercent =
      showPercent ?? (!isIndeterminate && value !== undefined);

    const percentText = formatValue
      ? formatValue(clampedValue, max, percentage)
      : `${percentage}%`;

    return (
      <div
        role="progressbar"
        aria-valuenow={isIndeterminate ? undefined : clampedValue}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={text ?? t("statuses.loading")}
        className={cn("flex w-full flex-col gap-2", className)}
      >
        {(text || shouldShowPercent) && (
          <div className="flex items-center justify-between gap-4">
            {text && (
              <span className="text-style-caption-strong text-color-foreground">
                {text}
              </span>
            )}
            {shouldShowPercent && (
              <span className="text-style-caption text-color-muted-foreground tabular-nums">
                {percentText}
              </span>
            )}
          </div>
        )}
        <div
          className={cn(
            "w-full overflow-hidden rounded-full bg-muted",
            progressTrackClasses[size],
            trackClassName,
          )}
        >
          {isIndeterminate ? (
            <div
              className={cn(
                "h-full w-full rounded-full bg-primary animate-pulse",
                indicatorClassName,
              )}
            />
          ) : (
            <div
              className={cn(
                "h-full rounded-full bg-primary transition-all duration-300 ease-out",
                indicatorClassName,
              )}
              style={{ width: `${percentage}%` }}
            />
          )}
        </div>
        {description && (
          <p className="text-style-caption text-color-muted-foreground">
            {description}
          </p>
        )}
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-col items-center justify-center text-center",
        className,
      )}
    >
      {icon ?? (
        <Loader2
          className={cn(
            "animate-spin text-color-primary",
            spinnerSizeClasses[size],
            spinnerClassName,
          )}
          aria-hidden="true"
        />
      )}
      {text && (
        <p className={cn("mt-3 text-color-foreground", spinnerTitleClasses[size])}>
          {text}
        </p>
      )}
      {description && (
        <p className="mt-1 max-w-sm text-style-caption text-color-muted-foreground">
          {description}
        </p>
      )}
      <span className="sr-only">{text ?? t("statuses.loading")}</span>
    </div>
  );
}

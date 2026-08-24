import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-surface border border-border bg-surface text-color-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col gap-1.5 p-5 pb-0", className)}
      {...props}
    />
  );
}

export function CardContent({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />;
}

export function CardFooter({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex items-center gap-3 p-5 pt-0", className)}
      {...props}
    />
  );
}

export function CardSummary({
  label,
  value,
  helper,
  icon,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  helper?: string;
  icon?: ReactNode;
  tone?: "default" | "success" | "warning" | "error" | "info";
}) {
  const iconColor =
    tone === "success"
      ? "text-color-success"
      : tone === "error"
        ? "text-color-danger"
        : tone === "warning"
          ? "text-color-warning"
          : tone === "info"
            ? "text-color-info"
            : "text-color-foreground-subtle";

  return (
    <div className="rounded-surface border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-style-overline uppercase text-color-foreground-subtle">
          {label}
        </p>
        <div className={iconColor}>{icon}</div>
      </div>
      <p
        className="mt-2 truncate text-style-metric text-color-foreground"
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </p>
      {helper && (
        <p
          className="mt-1 text-style-caption text-color-foreground-subtle truncate"
          title={helper}
        >
          {helper}
        </p>
      )}
    </div>
  );
}

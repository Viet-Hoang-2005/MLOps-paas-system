import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export interface PlaceholderProps {
  title?: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  additional?: ReactNode;
  additionalClassName?: string;
  className?: string;
  role?: string;
  children?: ReactNode;
}

export function Placeholder({
  title,
  description,
  icon,
  action,
  additional,
  additionalClassName,
  className,
  role,
  children,
}: PlaceholderProps) {
  return (
    <section
      role={role}
      className={cn(
        "flex flex-1 flex-col rounded-surface border border-dashed border-border bg-surface px-8 py-10",
        className,
      )}
    >
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        {icon && (
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-surface bg-muted text-color-foreground">
            {icon}
          </div>
        )}
        {additional &&
          (typeof additional === "string" || typeof additional === "number" ? (
            <p
              className={cn(
                "mb-2 text-style-overline uppercase text-color-muted-foreground",
                additionalClassName,
              )}
            >
              {additional}
            </p>
          ) : (
            <div
              className={cn(
                "mb-2 text-style-overline uppercase text-color-muted-foreground",
                additionalClassName,
              )}
            >
              {additional}
            </div>
          ))}
        {title && (
          <h1 className="mb-3 text-style-page-title font-bold text-color-foreground">
            {title}
          </h1>
        )}
        {description && (
          <p className="max-w-lg text-style-body text-color-muted-foreground">
            {description}
          </p>
        )}
        {children}
        {action && <div className="mt-6">{action}</div>}
      </div>
    </section>
  );
}

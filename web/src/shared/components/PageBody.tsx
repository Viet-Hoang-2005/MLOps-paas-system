import React from "react";
import { cn } from "@/shared/lib/cn";

export interface PageBodyProps {
  children: React.ReactNode;
  className?: string;
  title?: React.ReactNode;
  headerClassName?: string;
}

export function PageBody({
  children,
  className,
  title,
  headerClassName,
}: PageBodyProps) {
  return (
    <section
      className={cn(
        "flex flex-1 flex-col rounded-surface border border-border bg-surface text-color-foreground shadow-sm overflow-hidden",
        className,
      )}
    >
      {title && (
        <div
          className={cn(
            "px-6 py-4 border-b border-border bg-muted/50",
            headerClassName,
          )}
        >
          {typeof title === "string" ? (
            <h3 className="text-style-heading">{title}</h3>
          ) : (
            title
          )}
        </div>
      )}
      {children}
    </section>
  );
}

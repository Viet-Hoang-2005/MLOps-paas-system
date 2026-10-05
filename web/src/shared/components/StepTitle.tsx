import type { ElementType } from "react";
import { cn } from "@/shared/lib/cn";

export interface StepTitleProps {
  title: string;
  subtitle?: string;
  description?: string;
  icon?: ElementType;
  className?: string;
}

export function StepTitle({
  title,
  subtitle,
  description,
  icon: Icon,
  className,
}: StepTitleProps) {
  const text = subtitle || description;
  return (
    <div className={cn("mb-4", className)}>
      <h2 className="flex items-center gap-2 text-style-section-title text-color-foreground">
        {Icon && <Icon className="w-5 h-5 text-color-muted-foreground" />}
        {title}
      </h2>
      {text && (
        <p className="mt-1 text-style-body text-color-muted-foreground">
          {text}
        </p>
      )}
    </div>
  );
}

import { isValidElement, type ElementType, type ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export interface TitleProps {
  title: ReactNode;
  subtitle?: string;
  description?: string;
  icon?: ElementType | ReactNode;
  className?: string;
  badge?: ReactNode;
  action?: ReactNode;
}

export function Title({
  title,
  subtitle,
  description,
  icon,
  className,
  badge,
  action,
}: TitleProps) {
  const text = subtitle || description;
  let iconNode: ReactNode = null;
  if (isValidElement(icon)) {
    iconNode = icon;
  } else if (icon) {
    const Icon = icon as ElementType;
    iconNode = <Icon className="w-5 h-5 text-color-muted-foreground" />;
  }

  return (
    <div className={cn("mb-4", className)}>
      <div
        className={cn(
          "flex flex-wrap justify-between gap-3",
          text ? "items-start" : "items-center",
        )}
      >
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-style-section-title text-color-foreground">
            {iconNode}
            <span>{title}</span>
            {badge}
          </h2>
          {text && (
            <p className="mt-1 text-style-body text-color-muted-foreground">
              {text}
            </p>
          )}
        </div>
        {action}
      </div>
    </div>
  );
}

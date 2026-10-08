import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export interface InfoItemProps {
  label: ReactNode;
  value?: ReactNode;
  children?: ReactNode;
  icon?: ReactNode;
  className?: string;
  labelClassName?: string;
  valueClassName?: string;
}

export function InfoItem({
  label,
  value,
  children,
  icon,
  className,
  labelClassName,
  valueClassName,
}: InfoItemProps) {
  const content = value ?? children;

  return (
    <div className={cn("flex flex-col justify-start", className)}>
      <div
        className={cn(
          "flex items-center gap-1.5 text-style-body text-color-muted-foreground",
          labelClassName,
        )}
      >
        {icon}
        <span>{label}</span>
      </div>
      <div
        className={cn(
          "mt-1 flex min-h-7 items-center text-style-section-title text-color-foreground",
          valueClassName,
        )}
      >
        {content}
      </div>
    </div>
  );
}

export default InfoItem;


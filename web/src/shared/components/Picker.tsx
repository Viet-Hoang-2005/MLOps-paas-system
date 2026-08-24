import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export interface PickerOption<T> {
  value: T;
  title: ReactNode;
  description?: ReactNode;
}

export interface PickerProps<T> {
  value: T;
  onChange: (value: T) => void;
  options: PickerOption<T>[];
  className?: string;
}

export function Picker<T extends string | number>({
  value,
  onChange,
  options,
  className,
}: PickerProps<T>) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2", className)}>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-control border p-4 text-left transition-colors",
            value === option.value
              ? "border-primary bg-primary-subtle text-color-foreground"
              : "border-border bg-surface text-color-foreground hover:border-primary",
          )}
        >
          <span className="text-style-heading">{option.title}</span>
          {option.description && (
            <p className="mt-2 text-style-body text-color-muted-foreground">
              {option.description}
            </p>
          )}
        </button>
      ))}
    </div>
  );
}

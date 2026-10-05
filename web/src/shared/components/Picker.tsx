import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export interface PickerOption<T> {
  value: T;
  title: ReactNode;
  description?: ReactNode;
}

export interface PickerProps<T> {
  title?: ReactNode;
  value: T;
  onChange: (value: T) => void;
  options: PickerOption<T>[];
  className?: string;
  disabled?: boolean;
}

export function Picker<T extends string | number>({
  title,
  value,
  onChange,
  options,
  className,
  disabled = false,
}: PickerProps<T>) {
  const content = (
    <div className={cn("grid gap-4 sm:grid-cols-2", className)}>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-control border p-4 text-left transition-colors",
            value === option.value
              ? "border-primary bg-primary-subtle text-color-foreground"
              : "border-border bg-surface text-color-foreground hover:border-primary",
            disabled &&
              "cursor-not-allowed opacity-60 hover:border-border pointer-events-none",
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

  if (!title) {
    return content;
  }

  return (
    <div className="flex w-full flex-col gap-2">
      <label className="text-style-body-strong text-color-foreground">
        {title}
      </label>
      {content}
    </div>
  );
}

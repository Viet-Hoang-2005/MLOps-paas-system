import { cn } from "@/shared/lib/cn";
import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { useId, useState } from "react";

export interface SelectOption {
  value: string;
  label: ReactNode;
  badge?: ReactNode;
}

export interface SelectProps {
  id?: string;
  label?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  wrapperClassName?: string;
  disabled?: boolean;
  "aria-label"?: string;
}

export function Select({
  id,
  label,
  value,
  onChange,
  options,
  placeholder = "Select an option",
  className,
  wrapperClassName,
  disabled = false,
  "aria-label": ariaLabel,
}: SelectProps) {
  const generatedId = useId();
  const selectId = id || generatedId;
  const [open, setOpen] = useState(false);
  const selectedOption = options.find((opt) => opt.value === value);

  const selectNode = (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          id={selectId}
          type="button"
          disabled={disabled}
          aria-label={ariaLabel || (typeof label === "string" ? label : undefined)}
          className={cn(
            "flex h-14 w-full items-center justify-between gap-3 rounded-surface border bg-surface px-4 text-left text-style-body-strong transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20",
            open ? "border-ring" : "border-input hover:border-input-hover",
            !selectedOption
              ? "text-color-foreground-subtle"
              : "text-color-foreground",
            disabled &&
              "cursor-not-allowed opacity-60 hover:border-input pointer-events-none",
            className,
          )}
        >
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <span className="truncate">
              {selectedOption?.label || placeholder}
            </span>
            {selectedOption?.badge}
          </div>
          <ChevronDown className="h-4 w-4 shrink-0 text-color-foreground-subtle" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={8}
          className="z-50 w-(--radix-popover-trigger-width) rounded-surface border border-border bg-surface p-1 shadow-(--shadow-overlay) animate-fade-in"
        >
          <div className="max-h-72 overflow-y-auto">
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className="flex min-h-10 w-full items-center justify-between gap-3 rounded-compact px-3 py-2 text-left hover:bg-surface-hover active:bg-surface-active"
              >
                <div className="flex min-w-0 flex-1 items-center gap-2.5">
                  <span className="block truncate text-style-body-strong text-color-foreground">
                    {option.label}
                  </span>
                  {option.badge}
                </div>
                {value === option.value && (
                  <Check className="h-4 w-4 shrink-0 text-color-primary" />
                )}
              </button>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );

  if (!label) {
    return selectNode;
  }

  return (
    <div className={cn("flex w-full flex-col gap-2", wrapperClassName)}>
      <label
        htmlFor={selectId}
        className="text-style-body-strong text-color-foreground"
      >
        {label}
      </label>
      {selectNode}
    </div>
  );
}

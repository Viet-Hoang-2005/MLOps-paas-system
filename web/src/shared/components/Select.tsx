import { useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "@/shared/lib/cn";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
}

export function Select({
  value,
  onChange,
  options,
  placeholder = "Select an option",
  className,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const selectedOption = options.find((opt) => opt.value === value);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cn(
            "flex h-14 w-full items-center justify-between gap-3 rounded-control border bg-surface px-4 text-left text-style-body-strong transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20",
            open
              ? "border-ring"
              : "border-input hover:border-input-hover",
            !selectedOption ? "text-color-foreground-subtle" : "text-color-foreground",
            className,
          )}
        >
          <span className="truncate">
            {selectedOption?.label || placeholder}
          </span>
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
                <span className="block truncate text-style-body-strong text-color-foreground">
                  {option.label}
                </span>
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
}

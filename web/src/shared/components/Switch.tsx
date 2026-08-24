import { cn } from "@/shared/lib/cn";
import { type VariantProps } from "class-variance-authority";
import { switchVariants } from "./switchVariants";

export interface SegmentedControlOption<T extends string | number> {
  value: T;
  title: string;
}

export interface SwitchProps<T extends string | number>
  extends
    Omit<React.HTMLAttributes<HTMLDivElement>, "onChange">,
    VariantProps<typeof switchVariants> {
  value: T;
  onChange: (value: T) => void;
  options: readonly SegmentedControlOption<T>[];
  className?: string;
  ariaLabel?: string;
  fullWidth?: boolean;
}

export function Switch<T extends string | number>({
  value,
  onChange,
  options,
  className,
  ariaLabel,
  size = "md",
  fullWidth = false,
  ...props
}: SwitchProps<T>) {
  return (
    <div
      className={cn(
        "flex justify-center",
        fullWidth ? "w-full" : "inline-flex",
        className,
      )}
      {...props}
    >
      <div
        className={cn(
          "inline-flex rounded-control shadow-sm",
          fullWidth && "w-full",
        )}
        role="tablist"
        aria-label={ariaLabel}
      >
        {options.map((option, index) => {
          const isSelected = value === option.value;
          return (
            <button
              key={String(option.value)}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => onChange(option.value)}
              className={cn(
                switchVariants({ size, selected: isSelected }),
                index === 0
                  ? "rounded-l-control"
                  : index === options.length - 1
                    ? "rounded-r-control -ml-px"
                    : "-ml-px",
                fullWidth && "flex-1",
              )}
            >
              {option.title}
            </button>
          );
        })}
      </div>
    </div>
  );
}

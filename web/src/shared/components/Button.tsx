import { cn } from "@/shared/lib/cn";
import { buttonVariants } from "@/shared/lib/buttonVariants";
import { Slot, Slottable } from "@radix-ui/react-slot";
import type { VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, ReactNode } from "react";
export interface ButtonProps
  extends
    ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  fullWidth?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  border?: boolean;
}

export function Button({
  asChild = false,
  variant,
  size,
  fullWidth = false,
  loading = false,
  border = true,
  icon,
  children,
  className,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  const prefixNode = loading ? (
    <span
      className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
      aria-hidden="true"
    />
  ) : icon ? (
    <span
      className={cn(
        "shrink-0",
        !border &&
          "transition-transform duration-150 group-hover:scale-110 group-active:scale-95",
      )}
      aria-hidden="true"
    >
      {icon}
    </span>
  ) : null;

  const mergedClassName = cn(
    buttonVariants({ variant, size }),
    fullWidth && "w-full",
    !border && [
      "group border-transparent bg-transparent shadow-none transition-all duration-150 hover:border-transparent hover:bg-surface-hover active:border-transparent active:bg-surface-active disabled:border-transparent disabled:bg-transparent",
      variant === "danger"
        ? "text-color-danger hover:text-color-danger-hover active:text-color-danger-active"
        : variant === "primary"
          ? "text-color-primary hover:text-color-primary-hover active:text-color-primary-active"
          : "text-color-muted-foreground hover:text-color-foreground active:text-color-foreground",
    ],
    className,
  );

  if (asChild) {
    return (
      <Slot
        aria-busy={loading || undefined}
        className={mergedClassName}
        {...props}
      >
        {prefixNode ? (
          [
            prefixNode,
            <Slottable key="slottable">{children}</Slottable>,
          ]
        ) : (
          children
        )}
      </Slot>
    );
  }

  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={mergedClassName}
      {...props}
    >
      {prefixNode}
      {children}
    </button>
  );
}

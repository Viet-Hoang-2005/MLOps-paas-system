import { cn } from "@/shared/lib/cn";
import { buttonVariants } from "@/shared/types/buttonVariants";
import { Slot } from "@radix-ui/react-slot";
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
  const Component = asChild ? Slot : "button";
  return (
    <Component
      type={asChild ? undefined : type}
      disabled={asChild ? undefined : disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
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
      )}
      {...props}
    >
      {loading ? (
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
      ) : null}
      {children}
    </Component>
  );
}

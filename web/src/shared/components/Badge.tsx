import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import {
  CircleAlert,
  CircleCheck,
  CircleMinus,
  CircleX,
  CircleDot,
} from "lucide-react";

const badgeVariants = cva(
  "inline-flex items-center",
  {
    variants: {
      variant: {
        neutral: "text-color-foreground-muted",
        info: "text-color-info",
        primary: "text-color-info",
        success: "text-color-success",
        warning: "text-color-warning",
        danger: "text-color-danger",
      },
      size: {
        sm: "gap-1 px-1.5 py-0.5 text-style-caption",
        md: "gap-1.5 px-2 py-1 text-style-control",
        lg: "gap-2 px-2.5 py-1.5 text-style-heading",
      },
    },
    defaultVariants: {
      variant: "neutral",
      size: "md",
    },
  },
);

const variantIcons = {
  success: CircleCheck,
  info: CircleAlert,
  primary: CircleAlert,
  danger: CircleX,
  warning: CircleMinus,
  neutral: CircleDot,
} as const;

const variantBorderClasses = {
  neutral: "border-border bg-surface-muted",
  info: "border-info-border bg-info-subtle",
  primary: "border-info-border bg-info-subtle",
  success: "border-success-border bg-success-subtle",
  warning: "border-warning-border bg-warning-subtle",
  danger: "border-danger-border bg-danger-subtle",
} as const;

const iconSizeClasses = {
  sm: "h-3 w-3 shrink-0",
  md: "h-3.5 w-3.5 shrink-0",
  lg: "h-4 w-4 shrink-0",
} as const;

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  border?: boolean;
  icon?: ReactNode;
  hideIcon?: boolean;
}

export function Badge({
  className,
  variant = "neutral",
  size = "md",
  border = false,
  icon,
  hideIcon = false,
  children,
  ...props
}: BadgeProps) {
  const resolvedSize = size ?? "md";
  const resolvedVariant = variant ?? "neutral";
  const iconClass = iconSizeClasses[resolvedSize] ?? iconSizeClasses.md;

  let iconElement: ReactNode = null;
  if (!hideIcon) {
    if (icon !== undefined) {
      iconElement = icon;
    } else if (variant && variant in variantIcons) {
      const IconComponent = variantIcons[variant as keyof typeof variantIcons];
      if (IconComponent) {
        iconElement = <IconComponent className={iconClass} />;
      }
    }
  }

  const borderClasses = border
    ? [
        "rounded-full border",
        variantBorderClasses[resolvedVariant as keyof typeof variantBorderClasses] ??
          variantBorderClasses.neutral,
      ]
    : null;

  return (
    <span
      className={cn(
        badgeVariants({ variant, size }),
        borderClasses,
        className,
      )}
      {...props}
    >
      {iconElement}
      {children}
    </span>
  );
}

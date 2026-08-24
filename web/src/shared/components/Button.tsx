import { Slot } from '@radix-ui/react-slot';
import type { VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';
import { buttonVariants } from './buttonVariants';
export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  fullWidth?: boolean;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  asChild = false,
  variant,
  size,
  fullWidth = false,
  loading = false,
  icon,
  children,
  className,
  disabled,
  type = 'button',
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : 'button';
  return (
    <Component
      type={asChild ? undefined : type}
      disabled={asChild ? undefined : disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), fullWidth && 'w-full', className)}
      {...props}
    >
      {loading ? (
        <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
      ) : icon ? (
        <span className="shrink-0" aria-hidden="true">{icon}</span>
      ) : null}
      {children}
    </Component>
  );
}

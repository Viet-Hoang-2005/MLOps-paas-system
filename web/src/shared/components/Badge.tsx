import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';
import { cn } from '@/shared/lib/cn';

const badgeVariants = cva('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-style-caption-strong', {
  variants: {
    variant: {
      neutral: 'border-border bg-surface-muted text-color-foreground-muted',
      info: 'border-info-border bg-info-subtle text-color-info',
      primary: 'border-info-border bg-info-subtle text-color-info',
      success: 'border-success-border bg-success-subtle text-color-success',
      warning: 'border-warning-border bg-warning-subtle text-color-warning',
      danger: 'border-danger-border bg-danger-subtle text-color-danger',
    },
  },
  defaultVariants: { variant: 'neutral' },
});

export function Badge({ className, variant, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

import { cva } from 'class-variance-authority';

export const buttonVariants = cva(
  'inline-flex select-none items-center justify-center whitespace-nowrap border transition-[background-color,border-color,color,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-disabled disabled:text-color-foreground-disabled',
  {
    variants: {
      size: {
        sm: 'h-8 gap-1.5 rounded-control px-3 text-style-caption-strong',
        md: 'h-10 gap-2 rounded-control px-4 text-style-control',
        lg: 'h-12 gap-2 rounded-control px-5 text-style-control',
        icon: 'h-10 w-10 rounded-surface p-0',
      },
      variant: {
      primary: 'border-primary bg-primary text-color-primary-foreground hover:border-primary-hover hover:bg-primary-hover active:border-primary-active active:bg-primary-active',
        secondary: 'border-border bg-surface text-color-foreground shadow-sm hover:border-border-strong hover:bg-surface-hover active:bg-surface-active',
        outline: 'border-border bg-transparent text-color-foreground hover:border-border-strong hover:bg-surface-hover active:bg-surface-active',
        ghost: 'border-transparent bg-transparent text-color-foreground-muted hover:bg-surface-hover hover:text-color-foreground active:bg-surface-active',
        info: 'border-info bg-info text-color-info-foreground shadow-sm hover:border-info-hover hover:bg-info-hover active:border-info-active active:bg-info-active',
        success: 'border-success bg-success text-color-success-foreground shadow-sm hover:border-success-hover hover:bg-success-hover active:border-success-active active:bg-success-active',
        warning: 'border-warning bg-warning text-color-warning-foreground shadow-sm hover:border-warning-hover hover:bg-warning-hover active:border-warning-active active:bg-warning-active',
        danger: 'border-danger bg-danger text-color-danger-foreground shadow-sm hover:border-danger-hover hover:bg-danger-hover active:border-danger-active active:bg-danger-active',
        'info-outline': 'border-info bg-info-subtle text-color-foreground hover:border-info-hover hover:bg-info-subtle-hover active:border-info-active active:bg-info-subtle-active',
        'success-outline': 'border-success bg-success-subtle text-color-foreground hover:border-success-hover hover:bg-success-subtle-hover active:border-success-active active:bg-success-subtle-active',
        'warning-outline': 'border-warning bg-warning-subtle text-color-foreground hover:border-warning-hover hover:bg-warning-subtle-hover active:border-warning-active active:bg-warning-subtle-active',
        'danger-outline': 'border-danger bg-danger-subtle text-color-foreground hover:border-danger-hover hover:bg-danger-subtle-hover active:border-danger-active active:bg-danger-subtle-active',
      },
    },
    defaultVariants: { variant: 'primary', size: 'lg' },
  },
);

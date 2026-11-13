import { cn } from "@/shared/lib/cn";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
} from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { useTranslation } from "react-i18next";

export type AlertVariant =
  "info" | "success" | "warning" | "danger" | "primary" | "neutral";

export interface CalloutProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "title"
> {
  variant?: AlertVariant;
  title?: ReactNode;
  description?: ReactNode;
  icon?: ReactNode | false;
  closable?: boolean;
  onClose?: () => void;
  action?: ReactNode;
  titleClassName?: string;
  descriptionClassName?: string;
}

const variantStyles: Record<
  AlertVariant,
  {
    container: string;
    iconColor: string;
    defaultIcon: typeof Info;
  }
> = {
  info: {
    container: "border-l-4 border-info bg-info-subtle text-color-foreground",
    iconColor: "text-color-info",
    defaultIcon: Info,
  },
  success: {
    container:
      "border-l-4 border-success bg-success-subtle text-color-foreground",
    iconColor: "text-color-success",
    defaultIcon: CheckCircle2,
  },
  warning: {
    container:
      "border-l-4 border-warning bg-warning-subtle text-color-foreground",
    iconColor: "text-color-warning",
    defaultIcon: AlertTriangle,
  },
  danger: {
    container:
      "border-l-4 border-danger bg-danger-subtle text-color-foreground",
    iconColor: "text-color-danger",
    defaultIcon: AlertCircle,
  },
  primary: {
    container:
      "border-l-4 border-primary bg-primary-subtle text-color-foreground",
    iconColor: "text-color-primary",
    defaultIcon: Info,
  },
  neutral: {
    container:
      "border-l-4 border-border bg-surface-muted text-color-foreground",
    iconColor: "text-color-muted-foreground",
    defaultIcon: Info,
  },
};

export function Callout({
  variant = "info",
  title,
  description,
  icon,
  closable = false,
  onClose,
  action,
  titleClassName,
  descriptionClassName,
  children,
  className,
  ...props
}: CalloutProps) {
  const { t } = useTranslation("common");
  const config = variantStyles[variant];
  const IconComponent = config.defaultIcon;

  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-r-surface p-4 shadow-sm transition-all",
        config.container,
        className,
      )}
      {...props}
    >
      {icon !== false && (
        <span className={cn("shrink-0", config.iconColor)} aria-hidden="true">
          {icon ?? <IconComponent className="h-5 w-5" />}
        </span>
      )}
      <div className="min-w-0 flex-1 space-y-1">
        {title && (
          <h5
            className={cn(
              "text-style-heading-line-height text-color-foreground",
              titleClassName,
            )}
          >
            {title}
          </h5>
        )}
        {(description || children) && (
          <div
            className={cn(
              "text-style-body text-color-foreground-muted",
              descriptionClassName,
            )}
          >
            {description}
            {children}
          </div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
      {closable && (
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-compact p-1 text-color-foreground-subtle hover:bg-surface-hover hover:text-color-foreground active:bg-surface-active"
          aria-label={t("actions.close")}
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

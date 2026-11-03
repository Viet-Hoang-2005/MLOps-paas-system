import { ArrowLeft } from "lucide-react";
import React, { isValidElement, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/shared/components/Button";

export interface BackProps {
  title?: ReactNode;
  onBack?: () => void;
  to?: string;
  className?: string;
  titleClassName?: string;
  "aria-label"?: string;
  variant?: "auto" | "icon" | "inline";
}

export function Back({
  title,
  onBack,
  to,
  className = "",
  titleClassName = "",
  "aria-label": ariaLabelProp,
  variant = "auto",
}: BackProps) {
  const navigate = useNavigate();
  const { t } = useTranslation("common");

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (onBack) {
      onBack();
      return;
    }
    if (to) {
      navigate(to);
      return;
    }
    navigate(-1);
  };

  const defaultLabel = t("actions.back");
  const ariaLabel =
    ariaLabelProp || (typeof title === "string" ? title : defaultLabel);
  const tooltip =
    ariaLabelProp || (typeof title === "string" ? title : defaultLabel);

  if (variant === "icon" || (variant === "auto" && !title)) {
    return (
      <Button
        size="icon"
        variant="secondary"
        icon={<ArrowLeft className="h-5 w-5" />}
        border={false}
        onClick={handleClick}
        aria-label={ariaLabel}
        title={tooltip}
      />
    );
  }

  if (isValidElement(title)) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <button
          type="button"
          onClick={handleClick}
          className="h-8 w-8 inline-flex items-center justify-center rounded-control text-color-muted-foreground hover:text-color-foreground hover:bg-muted transition-colors cursor-pointer"
          aria-label={ariaLabel}
          title={tooltip}
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        {title}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`inline-flex items-center gap-2 text-style-body text-color-muted-foreground hover:text-color-foreground font-medium transition-colors cursor-pointer ${className}`}
      aria-label={ariaLabel}
      title={tooltip}
    >
      <ArrowLeft className="h-4 w-4" />
      {title !== undefined && title !== null && (
      <span className={titleClassName}>{title}</span>
      )}
    </button>
  );
}

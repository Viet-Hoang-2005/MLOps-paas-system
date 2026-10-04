import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageTabs } from "./PageTabs";
import { Button } from "./Button";
import React from "react";

export interface PageHeaderProps {
  title: string;
  back?: boolean;
  showBack?: boolean;
  onBack?: () => void;
  backLink?: {
    to?: string;
    label?: string;
  };
  tabs?: React.ComponentProps<typeof PageTabs>["tabs"];
  children?: React.ReactNode;
  actions?: React.ReactNode;
}

export function PageHeader({
  title,
  back = false,
  showBack,
  onBack,
  backLink,
  tabs,
  children,
  actions,
}: PageHeaderProps) {
  const navigate = useNavigate();
  const { t } = useTranslation("common");
  const hasBack = back || (showBack ?? false) || Boolean(backLink);

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };

  return (
    <header
      className={`flex min-h-10 flex-col gap-4 border-b border-border md:flex-row md:items-end md:justify-between ${!tabs ? "pb-2" : ""}`}
    >
      <div className={`flex items-center gap-2 ${tabs ? "mb-2" : ""}`}>
        {hasBack && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleBack}
            className="h-8 w-8 text-color-muted-foreground hover:text-color-foreground"
            aria-label={t("actions.back")}
            title={t("actions.back")}
            icon={<ArrowLeft className="h-5 w-5" />}
          />
        )}
        <h1 className="text-style-page-title text-color-foreground">{title}</h1>
      </div>

      {tabs && <PageTabs tabs={tabs} />}
      {children && !tabs && <div>{children}</div>}
      {actions && <div>{actions}</div>}
    </header>
  );
}

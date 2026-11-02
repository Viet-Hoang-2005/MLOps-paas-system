import { Back } from "./Back";
import { PageTabs } from "./PageTabs";
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
  const hasBack = back || (showBack ?? false) || Boolean(backLink);

  return (
    <header
      className={`flex min-h-10 flex-col gap-4 border-b border-border md:flex-row md:items-end md:justify-between ${!tabs ? "pb-2" : ""}`}
    >
      <div className={`flex items-center gap-2 ${tabs ? "mb-2" : ""}`}>
        {hasBack && (
          <Back
            onBack={onBack}
            to={backLink?.to}
            aria-label={backLink?.label}
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

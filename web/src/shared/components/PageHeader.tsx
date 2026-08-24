import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { PageTabs } from "./PageTabs";
import React from "react";

export interface PageHeaderProps {
  title: string;
  backLink?: {
    to: string;
    label: string;
  };
  tabs?: React.ComponentProps<typeof PageTabs>["tabs"];
  children?: React.ReactNode;
}

export function PageHeader({
  title,
  backLink,
  tabs,
  children,
}: PageHeaderProps) {
  return (
    <header
      className={`flex min-h-10 flex-col gap-4 border-b border-border md:flex-row md:items-end md:justify-between ${!tabs ? "pb-2" : ""}`}
    >
      <div className={tabs ? "mb-2" : ""}>
        {backLink && (
          <Link
            to={backLink.to}
            className="inline-flex min-h-9 items-center gap-2 rounded-control text-style-body-strong text-color-muted-foreground hover:text-color-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-4 w-4" />
            {backLink.label}
          </Link>
        )}
        <h1 className="text-style-page-title text-color-foreground">{title}</h1>
      </div>

      {tabs && <PageTabs tabs={tabs} />}
      {children && !tabs && <div>{children}</div>}
    </header>
  );
}

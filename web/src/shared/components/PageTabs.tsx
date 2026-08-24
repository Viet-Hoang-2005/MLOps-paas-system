import type { ComponentType } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export type PageTab = {
  label: string;
  icon?: ComponentType<{ className?: string }>;
  to?: string;
  onClick?: () => void;
  isActive?: boolean;
};

type PageTabsProps = {
  tabs: PageTab[];
};

export function PageTabs({ tabs }: PageTabsProps) {
  const { t } = useTranslation('common');
  return (
    <nav className="-mb-px w-full overflow-x-auto md:w-auto" aria-label={t('accessibility.pageSections')}>
      <div className="flex min-w-max items-center gap-2">
        {tabs.map((tab, idx) => {
          const Icon = tab.icon;
          const key = tab.to || tab.label + idx;

          if (tab.to) {
            return (
              <NavLink
                key={key}
                to={tab.to}
                className={({ isActive }) =>
                  [
                    'inline-flex h-10 items-center gap-2 border-b-2 px-3 text-style-body-strong transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                    isActive
                      ? 'border-primary text-color-primary'
                      : 'border-transparent text-color-muted-foreground hover:border-border hover:text-color-foreground',
                  ].join(' ')
                }
              >
                {Icon && <Icon className="h-4 w-4 shrink-0" />}
                <span className="whitespace-nowrap">{tab.label}</span>
              </NavLink>
            );
          }

          return (
            <button
              key={key}
              type="button"
              onClick={tab.onClick}
              className={[
                'inline-flex h-10 items-center gap-2 border-b-2 px-3 text-style-body-strong transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                tab.isActive
                  ? 'border-primary text-color-primary'
                  : 'border-transparent text-color-muted-foreground hover:border-border hover:text-color-foreground',
              ].join(' ')}
            >
              {Icon && <Icon className="h-4 w-4 shrink-0" />}
              <span className="whitespace-nowrap">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

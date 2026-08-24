import { Bell, Bot, BrainCircuit, GitBranch, Home, LineChart, LogOut, Menu, Settings, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { NavLink, useLocation } from 'react-router-dom';
import { routes } from '@/app/router/paths';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { cn } from '@/shared/lib/cn';

interface DashboardSidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggle: () => void;
  onCloseMobile: () => void;
}

const workspaceItems = [
  { key: 'home', to: routes.overview, icon: Home, match: '/dashboard/home' },
  { key: 'driftMonitoring', to: routes.monitoring, icon: LineChart, match: routes.monitoring },
  { key: 'modelTraining', to: routes.training, icon: BrainCircuit, match: routes.training },
  { key: 'modelEvolution', to: routes.registry, icon: GitBranch, match: routes.registry },
] as const;

const utilityItems = [
  { key: 'management', to: routes.deploy, icon: Bot, match: routes.deploy },
  { key: 'notification', to: routes.notifications, icon: Bell, match: routes.notifications },
  { key: 'setting', to: routes.profile, icon: Settings, match: '/dashboard/settings' },
] as const;

export default function Sidebar({ collapsed, mobileOpen, onToggle, onCloseMobile }: DashboardSidebarProps) {
  const location = useLocation();
  const { logout } = useAuth();
  const { t } = useTranslation('common');

  const itemClass = (match: string) => cn(
    'group flex h-10 items-center gap-3 rounded-compact px-3 text-style-body-strong transition-colors focus-visible:ring-2 focus-visible:ring-ring',
    location.pathname.startsWith(match)
      ? 'bg-primary text-color-primary-foreground'
      : 'text-color-muted-foreground hover:bg-muted hover:text-color-foreground',
    'md:justify-center md:px-0 xl:justify-start xl:px-3',
    collapsed && 'xl:justify-center xl:px-0',
  );

  const labelClass = cn('truncate md:hidden xl:block', collapsed && 'xl:hidden');

  const renderItem = (item: (typeof workspaceItems)[number] | (typeof utilityItems)[number]) => {
    const Icon = item.icon;
    return (
      <NavLink key={item.key} to={item.to} onClick={onCloseMobile} className={itemClass(item.match)} title={collapsed ? t(`navigation.${item.key}`) : undefined}>
        <Icon className="h-5 w-5 shrink-0" />
        <span className={labelClass}>{t(`navigation.${item.key}`)}</span>
      </NavLink>
    );
  };

  return (
    <>
      {mobileOpen && <button type="button" className="fixed inset-0 z-30 bg-overlay md:hidden" onClick={onCloseMobile} aria-label={t('actions.closeNavigation')} />}
      <aside className={cn(
        'fixed inset-y-0 left-0 z-40 flex w-56 flex-col border-r border-border bg-surface transition-[transform,width] duration-200 md:static md:z-20 md:w-17 md:translate-x-0 xl:w-56',
        mobileOpen ? 'translate-x-0' : '-translate-x-full',
        collapsed && 'xl:w-17',
      )}>
        <div className="flex h-16 items-center justify-between border-b border-border px-3 md:hidden">
          <span className="text-style-body text-color-muted-foreground">{t('navigation.workspace')}</span>
          <button type="button" onClick={onCloseMobile} className="flex h-10 w-10 items-center justify-center rounded-surface text-color-muted-foreground hover:bg-muted hover:text-color-foreground" aria-label={t('actions.closeNavigation')}><X className="h-5 w-5" /></button>
        </div>

        <div className="hidden h-12 items-center gap-1 border-b border-border p-3 md:flex md:justify-center xl:justify-start">
          <button type="button" onClick={onToggle} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-surface text-color-muted-foreground hover:text-color-foreground" aria-label={collapsed ? t('actions.expandSidebar') : t('actions.collapseSidebar')}>
            <Menu className="h-5 w-5" />
          </button>
          <span className={cn('text-style-body text-color-muted-foreground md:hidden xl:block', collapsed && 'xl:hidden')}>{t('navigation.workspace')}</span>
        </div>

        <nav className="flex min-h-0 flex-1 flex-col justify-between overflow-y-auto p-3" aria-label={t('navigation.primary')}>
          <div className="space-y-1">{workspaceItems.map(renderItem)}</div>
          <div className="mb-2 space-y-1">
            {utilityItems.map(renderItem)}
            <button type="button" onClick={logout} className={cn(
              'flex h-10 w-full items-center gap-3 rounded-surface px-3 text-style-body-strong text-color-muted-foreground transition-colors hover:bg-danger-subtle hover:text-color-danger md:justify-center md:px-0 xl:justify-start xl:px-3',
              collapsed && 'xl:justify-center xl:px-0',
            )} title={collapsed ? t('actions.logout') : undefined}>
              <LogOut className="h-5 w-5 shrink-0" />
              <span className={labelClass}>{t('actions.logout')}</span>
            </button>
          </div>
        </nav>
      </aside>
    </>
  );
}

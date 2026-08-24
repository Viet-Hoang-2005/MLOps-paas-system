import { Code, UserRound } from 'lucide-react';
import { Outlet } from 'react-router-dom';
import { PageHeader } from '@/shared/components/PageHeader';
import { useTranslation } from 'react-i18next';

export default function SettingsLayout() {
  const { t } = useTranslation('settings');
  const settingsTabs = [
    { label: t('profile'), to: '/dashboard/settings/profile', icon: UserRound },
    { label: t('developer'), to: '/dashboard/settings/developer', icon: Code },
  ];
  return (
    <div className="flex flex-1 flex-col space-y-6">
      <PageHeader title={t('title')} tabs={settingsTabs} />

      <Outlet />
    </div>
  );
}

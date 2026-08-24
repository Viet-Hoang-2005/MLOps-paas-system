import { FlaskConical, UploadCloud } from 'lucide-react';
import { Outlet } from 'react-router-dom';
import { PageHeader } from '@/shared/components/PageHeader';
import { useTranslation } from 'react-i18next';

export default function HomeLayout() {
  const { t } = useTranslation('catalog');
  const homeTabs = [
    { label: t('models'), to: '/dashboard/home/models', icon: UploadCloud },
    { label: t('testing'), to: '/dashboard/home/model-testing', icon: FlaskConical },
  ];
  return (
    <div className="flex flex-1 flex-col space-y-6">
      <PageHeader title={t('title')} tabs={homeTabs} />

      <Outlet />
    </div>
  );
}

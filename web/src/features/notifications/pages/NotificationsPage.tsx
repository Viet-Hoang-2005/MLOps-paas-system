import { Bell } from 'lucide-react';
import { PageHeader } from '@/shared/components/PageHeader';
import { Placeholder } from '@/shared/components/Placeholder';
import { useTranslation } from 'react-i18next';

export default function NotificationsPage() {
  const { t } = useTranslation('notifications');
  return (
    <section className="flex flex-1 flex-col gap-6">
      <PageHeader title={t('title')} />
      <Placeholder
        title={t('comingSoon')}
        description={t('description')}
        icon={<Bell className="h-6 w-6" />}
        showModelName={false}
      />
    </section>
  );
}

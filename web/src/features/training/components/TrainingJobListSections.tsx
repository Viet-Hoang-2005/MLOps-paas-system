import { useTranslation } from 'react-i18next';
import { Switch } from '@/shared/components/Switch';

export type TrainingStatusFilter = 'pending' | 'success' | 'failed' | 'all';

export function TrainingJobStatusFilter({
  value,
  onChange,
}: {
  value: TrainingStatusFilter;
  onChange: (value: TrainingStatusFilter) => void;
}) {
  const { t } = useTranslation('training');
  const options = [
    { title: t('statusFilter.all'), value: 'all' as const },
    { title: t('statusFilter.pending'), value: 'pending' as const },
    { title: t('statusFilter.success'), value: 'success' as const },
    { title: t('statusFilter.failed'), value: 'failed' as const },
  ];

  return (
    <Switch
      value={value}
      onChange={onChange}
      options={options}
      size="md"
      ariaLabel={t('statusFilter.label')}
    />
  );
}

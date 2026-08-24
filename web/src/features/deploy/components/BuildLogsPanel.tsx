import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { deployQueryKeys } from '@/features/deploy/queryKeys';
import { TerminalViewer } from '@/shared/components/TerminalViewer';

export function BuildLogsPanel({ modelId }: { modelId: string }) {
  const { t } = useTranslation('deploy');

  const { data } = useQuery<{ logs: string[]; updated_at: string }>({
    queryKey: deployQueryKeys.logs(modelId),
    enabled: false, // populated via WS
  });

  const logs = data?.logs ?? [];

  if (!logs.length) return null;

  return (
    <div className="mt-4">
      <TerminalViewer
        title={t('lifecycle.buildLogs')}
        placeholder={t('lifecycle.waitingLogs')}
        logs={logs}
      />
    </div>
  );
}

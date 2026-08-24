/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState, useCallback } from 'react';
import { getRegistryHistory } from '@/features/registry/api/registryApi';
import { formatVersion } from '@/shared/lib/formatters';
import type { RegistryHistory } from '@/features/registry/types';
import { getApiErrorMessage } from '@/shared/api/errors';
import { toast } from '@/shared/components/toastStore';
import { GitCommit, ArrowUpRight, RotateCcw, Package, CheckCircle, XCircle, Trash2, Activity } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const classNames = (...classes: (string | undefined | null | false)[]) => classes.filter(Boolean).join(' ');

interface Props {
  familyId: string;
}

export function ModelHistoryTimeline({ familyId }: Props) {
  const [history, setHistory] = useState<RegistryHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const { t } = useTranslation('registry');

  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getRegistryHistory(familyId);
      setHistory(data);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('historyTimeline.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [familyId, t]);

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="h-8 w-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="text-center py-16 flex flex-col items-center border border-dashed border-border rounded-surface bg-muted/50 px-4">
        <div className="rounded-full bg-surface border border-border p-4 mb-4 shadow-sm">
          <GitCommit className="h-8 w-8 text-color-muted-foreground" />
        </div>
        <h3 className="text-style-heading font-bold text-color-foreground">{t('historyTimeline.emptyTitle')}</h3>
        <p className="mt-2 text-style-body text-color-muted-foreground max-w-md">
          {t('historyTimeline.emptyDescription')}
        </p>
      </div>
    );
  }

  return (
    <div className="relative border-l border-border ml-3 py-4 space-y-8">
      {history.map((event, idx) => {
        const isSuccess = event.status === 'success';
        const isFailed = event.status === 'failed';
        
        let Icon = GitCommit;
        let iconBg = 'bg-muted text-color-muted-foreground border-border';

        // Action-based styling
        if (event.action === 'promoted') {
          Icon = ArrowUpRight;
          iconBg = 'bg-success-subtle text-color-success border-success/20';
        } else if (event.action === 'rolled_back') {
          Icon = RotateCcw;
          iconBg = 'bg-warning-subtle text-color-warning border-warning/20';
        } else if (event.action === 'registered') {
          Icon = Package;
          iconBg = 'bg-primary-subtle text-color-primary border-primary/20';
        } else if (event.action === 'health_checked') {
          Icon = Activity;
          iconBg = 'bg-primary-subtle text-color-primary border-primary/20';
        } else if (event.action === 'archived' || event.action === 'stopped') {
          Icon = Trash2;
          iconBg = 'bg-muted text-color-muted-foreground border-border';
        }

        // Status overrides
        if (isFailed) {
          Icon = XCircle;
          iconBg = 'bg-danger-subtle text-color-danger border-danger/20';
        } else if (event.action === 'deployed' && isSuccess) {
          Icon = CheckCircle;
          iconBg = 'bg-success-subtle text-color-success border-success/20';
        }

        let actionText = event.action.replace('_', ' ');
        if (event.action === 'registered') actionText = t('historyTimeline.registered');
        else if (event.action === 'built') actionText = t('historyTimeline.built');
        else if (event.action === 'deployed') actionText = t('historyTimeline.deployed');
        else if (event.action === 'promoted') actionText = t('historyTimeline.promoted');
        else if (event.action === 'rolled_back') actionText = t('historyTimeline.rolledBack', { version: formatVersion(event.version) });
        else if (event.action === 'stopped') actionText = t('historyTimeline.stopped');
        
        if (isFailed) actionText = t('historyTimeline.failed');

        const renderTransition = () => {
          if (!event.from_stage && !event.to_stage) return null;

          if (event.action === 'promoted' || event.action === 'rolled_back') {
            const from = !event.from_stage || event.from_stage === 'none' ? t('historyTimeline.noProduction') : formatVersion(event.from_stage);
            const to = event.to_stage && event.to_stage !== 'production' ? formatVersion(event.to_stage) : formatVersion(event.version);
            
            return (
              <span className="text-style-caption text-color-muted-foreground font-medium">
                {t('historyTimeline.previousCurrent', { previous: from, current: to })}
              </span>
            );
          }

          return (
            <span className="text-style-caption text-color-muted-foreground font-medium">
              {event.from_stage} &rarr; {event.to_stage}
            </span>
          );
        };

        return (
          <div key={event.id || idx} className="relative pl-8">
            <span 
              className={classNames(
                "absolute -left-4 top-1 flex h-8 w-8 items-center justify-center rounded-full border ring-4 ring-surface shadow-sm",
                iconBg
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-style-body-strong text-color-foreground">{actionText}</span>
                <span className="font-mono text-style-code-sm font-semibold bg-muted border border-border px-2 py-0.5 rounded-compact text-color-foreground">{formatVersion(event.version)}</span>
                {renderTransition()}
                <span className="text-style-caption-strong text-color-muted-foreground ml-auto">
                  {new Date(event.created_at).toLocaleString()}
                </span>
              </div>
              
              {event.action === 'promoted' || event.action === 'rolled_back' ? (
                <p className="text-style-body text-color-muted-foreground">{t('historyTimeline.productionMarkerUpdated')}</p>
              ) : (
                <p className="text-style-body text-color-muted-foreground">{event.message}</p>
              )}
              
              {event.actor && (
                <p className="text-style-caption-strong text-color-muted-foreground">
                  {t('historyTimeline.by', { actor: event.actor })}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

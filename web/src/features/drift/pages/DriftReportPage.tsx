import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { PageHeader } from '@/shared/components/PageHeader';
import { PageBody } from '@/shared/components/PageBody';
import { Button } from '@/shared/components/Button';
import { getDriftReportDownloadUrl } from '@/features/drift/api/driftApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { toast } from '@/shared/components/toastStore';
import { useTranslation } from 'react-i18next';

export default function DriftReportPage() {
  const { modelId, runId } = useParams<{ modelId: string; runId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('drift');

  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) {
      toast.error(t('reportPage.missingRun'));
      navigate(`/dashboard/drift-monitoring/${modelId}`);
      return;
    }

    getDriftReportDownloadUrl(runId)
      .then(url => {
        setReportUrl(url);
        setLoading(false);
      })
      .catch(err => {
        toast.error(getApiErrorMessage(err, t('reportPage.urlFailed')));
        setLoading(false);
      });
  }, [runId, modelId, navigate, t]);

  const handleDownload = async () => {
    if (!reportUrl) return;
    try {
      const response = await fetch(reportUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `drift-report-${modelId}.html`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      const message = error instanceof Error ? error.message : t('reportPage.downloadFailed');
      toast.error(message);
      window.open(reportUrl, '_blank');
    }
  };

  return (
    <div className="flex w-full flex-1 flex-col min-h-0 space-y-6">
      <PageHeader 
        title={t('reportPage.title')}
        backLink={{ to: `/dashboard/drift-monitoring/${modelId}`, label: t('reportPage.back') }}
      >
        {reportUrl && (
          <Button size="md" icon={<Download className='w-4 h-4'/>} onClick={handleDownload}>
            {t('reportPage.download')}
          </Button>
        )}
      </PageHeader>
      
      <PageBody className="flex-1 overflow-hidden bg-muted flex items-center justify-center relative p-0 border-t border-border min-h-0">
        {loading ? (
          <div className="flex flex-col items-center justify-center text-color-muted-foreground">
            <Loader2 className="w-8 h-8 animate-spin mb-2" />
            <p>{t('reportPage.loading')}</p>
          </div>
        ) : reportUrl ? (
          <iframe 
            src={reportUrl} 
            title={t('reportPage.frameTitle')}
            className="absolute inset-0 w-full h-full border-0"
          />
        ) : (
          <div className="py-20 text-color-danger">{t('reportPage.loadFailed')}</div>
        )}
      </PageBody>
    </div>
  );
}

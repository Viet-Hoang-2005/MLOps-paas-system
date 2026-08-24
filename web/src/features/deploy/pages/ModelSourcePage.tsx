import { FileCode2, Database } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ModelProject } from '@/features/catalog/types';
import { SourceEditor } from '@/features/catalog/components/SourceEditor';

interface ModelSourcePageProps {
  model: ModelProject;
  setSourceCodeDirty: (dirty: boolean) => void;
  setReferenceDataDirty: (dirty: boolean) => void;
}

export function ModelSourcePage({
  model,
  setSourceCodeDirty,
  setReferenceDataDirty,
}: ModelSourcePageProps) {
  const { t } = useTranslation('deploy');
  return (
    <div className="flex-1 w-full h-full min-h-150 flex flex-col gap-6">
      <SourceEditor 
        modelId={model.id.toString()} 
        fileType="code_file"
        title={t('source.code')}
        icon={<FileCode2 className="w-4 h-4" />}
        accept=".zip,.py"
        editorType="code"
        onDirtyChange={setSourceCodeDirty}
      />
      <SourceEditor
        modelId={model.id.toString()} 
        fileType="data_file"
        title={t('source.referenceData')}
        icon={<Database className="w-4 h-4" />}
        accept=".zip,.csv"
        editorType="csv"
        onDirtyChange={setReferenceDataDirty}
      />
    </div>
  );
}

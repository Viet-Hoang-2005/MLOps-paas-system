import { Picker } from '@/shared/components/Picker';
import { useTranslation } from 'react-i18next';
import type { ModelProject, ProjectMetadataForm } from '@/features/catalog/types';
import { FileDropzone } from '@/shared/components/FileDropzone';
import { Input } from '@/shared/components/Input';
import { StepTitle } from '@/shared/components/StepTitle';
import { TextArea } from '@/shared/components/TextArea';

interface ProjectMetadataFieldsProps {
  form: ProjectMetadataForm;
  project?: ModelProject | null;
  setField: <K extends keyof ProjectMetadataForm>(field: K, value: ProjectMetadataForm[K]) => void;
}

export function ProjectMetadataFields({ form, project, setField }: ProjectMetadataFieldsProps) {
  const { t } = useTranslation('deploy');
  return (
    <div className="flex flex-col gap-8">
      <section className="space-y-5">
        <StepTitle title={t('uploadFlow.metadata.title')} description={t('uploadFlow.metadata.description')} />
        <Input
          id="metadata-name"
          label={t('uploadFlow.metadata.name')}
          value={form.name}
          onChange={(event) => setField('name', event.target.value)}
          placeholder={t('uploadFlow.metadata.namePlaceholder')}
        />
        <TextArea
          id="metadata-description"
          label={t('uploadFlow.metadata.modelDescription')}
          value={form.description}
          onChange={(value) => setField('description', value)}
          placeholder={t('uploadFlow.metadata.descriptionPlaceholder')}
        />
        <Picker
          value={form.access_mode}
          onChange={(value) => setField('access_mode', value as ProjectMetadataForm['access_mode'])}
          options={[
            { value: 'private', title: t('access.privateTitle'), description: t('access.privateDescription') },
            { value: 'public', title: t('access.publicTitle'), description: t('access.publicDescription') },
          ]}
        />
      </section>

      <hr className="border-border" />

      <section className="space-y-5">
        <StepTitle title={t('uploadFlow.metadata.sourcesTitle')} description={t('uploadFlow.metadata.sourcesDescription')} />
        <FileDropzone
          accept=".zip,.py"
          title={form.source_code_file?.name || project?.source_code?.name || t('uploadFlow.metadata.sourceCode')}
          subtitle={t('uploadFlow.metadata.sourceHint')}
          onChange={(file) => setField('source_code_file', file)}
        />
        <FileDropzone
          accept=".zip,.csv,.parquet"
          title={form.reference_data_file?.name || project?.reference_data?.name || t('uploadFlow.metadata.referenceData')}
          subtitle={t('uploadFlow.metadata.referenceHint')}
          onChange={(file) => setField('reference_data_file', file)}
        />
      </section>
    </div>
  );
}

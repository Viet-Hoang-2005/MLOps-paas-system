import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { Button } from '@/shared/components/Button';
import { Input } from '@/shared/components/Input';
import { TextArea } from '@/shared/components/TextArea';
import { Picker } from '@/shared/components/Picker';
import type { ModelProject, ModelProjectFormValues } from '@/features/catalog/types';
import { useModelProjectMutations } from '@/features/catalog/hooks/useModelProjects';

export default function EditModelModal({
  model,
  visible,
  onClose,
}: {
  model: ModelProject | null;
  visible: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation('deploy');
  const { updateModelProject, updating } = useModelProjectMutations();
  const [form, setForm] = useState<ModelProjectFormValues>({
    name: model?.name || '',
    description: model?.description || '',
    access_mode: model?.access_mode || 'public',
  });

  useEffect(() => {
    if (visible) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [visible]);



  if (!visible || !model) return null;

  const setField = (field: keyof ModelProjectFormValues, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const isDirty = 
    form.name !== model.name ||
    form.description !== model.description ||
    form.access_mode !== model.access_mode;

  const handleSave = () => {
    if (!isDirty) return;
    updateModelProject({ modelId: model.id, payload: form });
    onClose();
  };

  const handleCancel = () => {
    setForm({
      name: model.name,
      description: model.description,
      access_mode: model.access_mode,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4">
      <div 
        className="w-full max-w-xl bg-surface rounded-overlay shadow-xl flex flex-col max-h-[85vh] overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4 shrink-0">
          <h2 className="text-style-section-title font-bold text-color-foreground">{t('editModel.title')}</h2>
          <button 
            onClick={handleCancel}
            className="text-color-muted-foreground hover:text-color-muted-foreground transition-colors p-1"
          >
            <X className="h-6 w-6" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="flex flex-col h-full w-full">
            <div className="flex-1 space-y-5">
              <Input
                label={t('editModel.name')}
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
              />
              <TextArea
                id="edit-desc"
                label={t('editModel.description')}
                value={form.description}
                onChange={(v) => setField('description', v)}
                placeholder=""
              />
              <div>
                <label className="text-style-body-strong text-color-foreground mb-2 block">{t('editModel.accessMode')}</label>
                <Picker
                  value={form.access_mode}
                  onChange={(v) => setField('access_mode', v as ModelProjectFormValues['access_mode'])}
                  options={[
                    { value: 'private', title: t('editModel.privateTitle'), description: t('editModel.privateDescription') },
                    { value: 'public', title: t('editModel.publicTitle'), description: t('editModel.publicDescription') },
                  ]}
                />
              </div>
            </div>
            
            <div className="mt-8 flex items-center justify-end gap-3 border-t border-border pt-6">
              <Button
                variant="secondary"
                size="md"
                onClick={handleCancel}
              >
                {t('actions.cancel', { ns: 'common' })}
              </Button>
              <Button
                size="md"
                loading={updating}
                disabled={!isDirty}
                onClick={handleSave}
              >
                {t('actions.save', { ns: 'common' })}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

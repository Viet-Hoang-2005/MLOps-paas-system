import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { createAPIKey, updateAPIKey } from '@/features/settings/api/apiKeysApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { settingsQueryKeys } from '@/features/settings/queryKeys';
import { toast } from '@/shared/components/toastStore';
import type { APIKeyRecord, CreatedAPIKeyResponse } from '@/features/settings/types';
import { useTranslation } from 'react-i18next';

export function useApiKeyForm(initialData?: APIKeyRecord | null) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { t } = useTranslation('settings');
  const [apiKeyName, setApiKeyName] = useState(initialData?.name || '');
  const [apiKeyDescription, setApiKeyDescription] = useState(initialData?.description || '');
  const [apiKeyScope, setApiKeyScope] = useState(initialData?.scope || 'all');
  const [apiKeyModels, setApiKeyModels] = useState<string[]>(initialData?.allowed_models || []);
  const [createdApiKey, setCreatedApiKey] = useState<CreatedAPIKeyResponse | null>(null);

  const [prevInitialData, setPrevInitialData] = useState(initialData);

  if (initialData !== prevInitialData) {
    setPrevInitialData(initialData);
    if (initialData) {
      setApiKeyName(initialData.name || '');
      setApiKeyDescription(initialData.description || '');
      setApiKeyScope(initialData.scope || 'all');
      setApiKeyModels(initialData.allowed_models || []);
    }
  }

  const refreshAPIKeys = async () => {
    await queryClient.invalidateQueries({ queryKey: settingsQueryKeys.apiKeys() });
  };

  const createAPIKeyMutation = useMutation({
    mutationFn: createAPIKey,
    onSuccess: async (response) => {
      setCreatedApiKey(response);
      await refreshAPIKeys();
      toast.success(t('apiKey.createSuccess'));
      // Navigation is handled by the component after the user copies the key
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('apiKey.createFailed')));
    },
  });

  const updateAPIKeyMutation = useMutation({
    mutationFn: ({ id, name, description, scope, allowed_models }: { id: string; name: string; description: string, scope: string, allowed_models: string[] }) =>
      updateAPIKey(id, { name, description, scope, allowed_models }),
    onSuccess: async () => {
      toast.success(t('apiKey.updateSuccess'));
      await refreshAPIKeys();
      navigate('/dashboard/settings/developer');
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('apiKey.updateFailed')));
    },
  });

  const handleSaveAPIKey = () => {
    if (!apiKeyName.trim()) {
      toast.warning(t('apiKey.nameRequired'));
      return;
    }

    if (apiKeyModels.length === 0) {
      toast.warning(t('apiKey.modelRequired'));
      return;
    }


    if (initialData) {
      updateAPIKeyMutation.mutate({
        id: initialData.id,
        name: apiKeyName.trim(),
        description: apiKeyDescription.trim(),
        scope: apiKeyScope,
        allowed_models: apiKeyModels,
      });
    } else {
      createAPIKeyMutation.mutate({
        name: apiKeyName.trim(),
        description: apiKeyDescription.trim(),
        scope: apiKeyScope,
        allowed_models: apiKeyModels,
      });
    }
  };

  const saving = createAPIKeyMutation.isPending || updateAPIKeyMutation.isPending;

  return {
    apiKeyName,
    setApiKeyName,
    apiKeyDescription,
    setApiKeyDescription,
    apiKeyScope,
    setApiKeyScope,
    apiKeyModels,
    setApiKeyModels,
    createdApiKey,
    setCreatedApiKey,
    handleSaveAPIKey,
    saving,
  };
}

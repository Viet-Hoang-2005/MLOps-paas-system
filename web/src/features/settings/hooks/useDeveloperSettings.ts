import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteAPIKey,
  listAPIKeys,
  regenerateAPIKey,
} from '@/features/settings/api/apiKeysApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { settingsQueryKeys } from '@/features/settings/queryKeys';
import { toast } from '@/shared/components/toastStore';
import type { APIKeyRecord, CreatedAPIKeyResponse } from '@/features/settings/types';
import { useTranslation } from 'react-i18next';

export function useDeveloperSettings() {
  const queryClient = useQueryClient();
  const { t } = useTranslation('settings');
  const [createdApiKey, setCreatedApiKey] = useState<CreatedAPIKeyResponse | null>(null);

  const apiKeysQuery = useQuery({
    queryKey: settingsQueryKeys.apiKeys(),
    queryFn: listAPIKeys,
  });

  useEffect(() => {
    if (apiKeysQuery.isError) {
      toast.error(getApiErrorMessage(apiKeysQuery.error, t('apiKey.loadFailed')));
    }
  }, [apiKeysQuery.error, apiKeysQuery.isError, t]);

  const refreshAPIKeys = async () => {
    await queryClient.invalidateQueries({ queryKey: settingsQueryKeys.apiKeys() });
  };


  const deleteAPIKeyMutation = useMutation({
    mutationFn: deleteAPIKey,
    onSuccess: async () => {
      toast.success(t('apiKey.deleteSuccess'));
      await refreshAPIKeys();
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('apiKey.deleteFailed')));
    },
  });

  const regenerateAPIKeyMutation = useMutation({
    mutationFn: regenerateAPIKey,
    onSuccess: async (response) => {
      setCreatedApiKey(response);
      await refreshAPIKeys();
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('apiKey.regenerateFailed')));
    },
  });


  const handleDeleteAPIKey = async (apiKey: APIKeyRecord) => {
    deleteAPIKeyMutation.mutate(apiKey.id);
  };

  const handleRegenerateAPIKey = async (apiKey: APIKeyRecord) => {
    regenerateAPIKeyMutation.mutate(apiKey.id);
  };

  const handleCopyCreatedKey = async () => {
    if (!createdApiKey?.api_key) return;
    try {
      await navigator.clipboard.writeText(createdApiKey.api_key);
      toast.success(t('apiKey.copied'));
    } catch {
      toast.warning(t('apiKey.copyFailed'));
    }
  };

  return {
    apiKeys: apiKeysQuery.data?.api_keys ?? [],
    loading: apiKeysQuery.isLoading,
    createdApiKey,
    setCreatedApiKey,
    handleDeleteAPIKey,
    handleRegenerateAPIKey,
    handleCopyCreatedKey,
  };
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  createModelProject,
  deleteModelProject,
  listModelProjects,
  updateModelProject,
} from '@/features/catalog/api/catalogApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { catalogQueryKeys } from '@/features/catalog/queryKeys';
import { toast } from '@/shared/components/toastStore';
import type { ModelProjectFormValues } from '@/features/catalog/types';

export function useModelProjects() {
  return useQuery({
    queryKey: catalogQueryKeys.projects(),
    queryFn: listModelProjects,
  });
}

export function useModelProjectMutations() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { t } = useTranslation('catalog');

  const invalidateModels = () => queryClient.invalidateQueries({ queryKey: catalogQueryKeys.projects() });

  const createMutation = useMutation({
    mutationFn: createModelProject,
    onSuccess: async () => {
      await invalidateModels();
      toast.success(t('messages.createSuccess'));
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('messages.createFailed')));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ modelId, payload }: { modelId: string; payload: ModelProjectFormValues }) =>
      updateModelProject(modelId, payload),
    onSuccess: async () => {
      await invalidateModels();
      toast.success(t('messages.updateSuccess'));
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('messages.updateFailed')));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (modelId: string) => deleteModelProject(modelId, true),
    onSuccess: async () => {
      await invalidateModels();
      toast.success(t('messages.deleteStarted'));
      navigate('/dashboard/management');
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('messages.deleteFailed')));
    },
  });

  return {
    createModelProject: createMutation.mutateAsync,
    updateModelProject: updateMutation.mutateAsync,
    deleteModelProject: deleteMutation.mutateAsync,
    creating: createMutation.isPending,
    updating: updateMutation.isPending,
    deleting: deleteMutation.isPending,
  };
}

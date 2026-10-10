import {
  cancelDriftMonitoringJob,
  cancelDriftMonitoringRun,
  createDriftMonitoringJob,
  deleteDriftMonitoringJob,
  deleteDriftMonitoringRun,
  getDriftMonitor,
  getDriftReportData,
  getProductionDataCount,
  listDriftMonitoringJobs,
  listDriftMonitoringResults,
  listProductionData,
  runDriftMonitoringJob,
  updateDriftMonitoringJob,
} from "@/features/monitoring/api/driftApi";
import { driftQueryKeys } from "@/features/monitoring/queryKeys";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

export type {
  DriftMonitoringJob,
  DriftMonitoringResult,
} from "@/features/monitoring/types";

export function useDriftMonitoringJobs(modelId?: string) {
  return useQuery({
    queryKey: driftQueryKeys.monitors(modelId ?? ""),
    queryFn: () => listDriftMonitoringJobs(modelId!),
    enabled: Boolean(modelId),
    refetchInterval: 15000,
  });
}

export function useDriftMonitor(jobId?: string) {
  return useQuery({
    queryKey: driftQueryKeys.configuration(jobId ?? ""),
    queryFn: () => getDriftMonitor(jobId!),
    enabled: Boolean(jobId),
  });
}

export function useDriftMonitoringResults(jobId?: string) {
  return useQuery({
    queryKey: driftQueryKeys.results(jobId ?? ""),
    queryFn: () => listDriftMonitoringResults(jobId!),
    enabled: Boolean(jobId),
  });
}

export function useCreateDriftMonitoringJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDriftMonitoringJob,
    onSuccess: (_, variables) =>
      queryClient.invalidateQueries({
        queryKey: driftQueryKeys.monitors(variables.project_id),
      }),
  });
}

export function useDeleteDriftMonitoringJob() {
  const queryClient = useQueryClient();
  const { t } = useTranslation("monitoring");
  return useMutation({
    mutationFn: async (payload: { id: string; project_id: string }) =>
      deleteDriftMonitoringJob(payload.id),
    onSuccess: (_, variables) => {
      toast.success(t("messages.deleted"));
      queryClient.invalidateQueries({
        queryKey: driftQueryKeys.monitors(variables.project_id),
      });
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, t("messages.deleteFailed"))),
  });
}

export function useUpdateDriftMonitoringJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateDriftMonitoringJob,
    onSuccess: (_, variables) =>
      queryClient.invalidateQueries({
        queryKey: driftQueryKeys.monitors(variables.project_id),
      }),
  });
}

export function useRunDriftMonitoringJob() {
  const queryClient = useQueryClient();
  const { t } = useTranslation("monitoring");
  return useMutation({
    mutationFn: async (payload: { id: string; project_id: string }) =>
      runDriftMonitoringJob(payload.id),
    onSuccess: (_, variables) => {
      toast.success(t("messages.runQueued"));
      void queryClient.invalidateQueries({
        queryKey: driftQueryKeys.results(variables.id),
      });
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, t("messages.runFailed"))),
  });
}

export function useProductionData(modelId?: string, versionId?: string) {
  return useQuery({
    queryKey: driftQueryKeys.productionData(modelId ?? "", versionId, 100),
    queryFn: () => listProductionData(modelId!, 100, versionId),
    enabled: Boolean(modelId),
  });
}

export function useProductionDataCount(projectId?: string, versionId?: string) {
  return useQuery({
    queryKey: [...driftQueryKeys.all, "production-count", projectId ?? "", versionId ?? ""],
    queryFn: () => getProductionDataCount(projectId!, versionId),
    enabled: Boolean(projectId),
    refetchInterval: 15000,
  });
}

export function useDeleteDriftMonitoringRun(monitorId?: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation("monitoring");
  return useMutation({
    mutationFn: async (runId: string) => deleteDriftMonitoringRun(runId),
    onSuccess: () => {
      toast.success(t("messages.runDeleted"));
      if (monitorId) {
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.results(monitorId),
        });
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.configuration(monitorId),
        });
      }
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, t("messages.runDeleteFailed"))),
  });
}

export function useCancelDriftMonitoringRun(monitorId?: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation("monitoring");
  return useMutation({
    mutationFn: async ({
      runId,
      monitorId: mId,
    }: {
      runId?: string;
      monitorId?: string;
    }) => {
      if (runId) {
        return cancelDriftMonitoringRun(runId);
      }
      if (mId) {
        return cancelDriftMonitoringJob(mId);
      }
      throw new Error("Missing runId or monitorId");
    },
    onSuccess: () => {
      toast.success(t("messages.runCancelled"));
      const targetMonitorId = monitorId;
      if (targetMonitorId) {
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.results(targetMonitorId),
        });
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.configuration(targetMonitorId),
        });
      }
      void queryClient.invalidateQueries({
        queryKey: driftQueryKeys.all,
      });
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, t("messages.runCancelFailed"))),
  });
}

export function useDriftReportData(runId?: string) {
  return useQuery({
    queryKey: driftQueryKeys.reportData(runId ?? ""),
    queryFn: () => getDriftReportData(runId!),
    enabled: Boolean(runId),
  });
}



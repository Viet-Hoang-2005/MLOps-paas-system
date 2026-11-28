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
  listProductionData,
  runDriftMonitoringJob,
  updateDriftMonitoringJob,
} from "@/features/monitoring/api/driftApi";
import { driftQueryKeys } from "@/features/monitoring/queryKeys";
import type { DriftMonitoringJob } from "@/features/monitoring/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
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
    queryKey: driftQueryKeys.detail(jobId ?? ""),
    queryFn: async () => {
      try {
        return await getDriftMonitor(jobId!);
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 404) return null;
        throw error;
      }
    },
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const monitor = query.state.data;
      return monitor ? (monitor.deletion_requested ? 3000 : 15000) : false;
    },
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
    onSuccess: async (_, variables) => {
      const listKey = driftQueryKeys.monitors(variables.project_id);
      const detailKey = driftQueryKeys.detail(variables.id);
      await Promise.all([
        queryClient.cancelQueries({ queryKey: listKey }),
        queryClient.cancelQueries({ queryKey: detailKey }),
      ]);
      queryClient.setQueryData<DriftMonitoringJob[]>(listKey, (jobs) =>
        jobs?.map((job) =>
          job.id === variables.id ? { ...job, deletion_requested: true } : job,
        ),
      );
      queryClient.setQueryData<DriftMonitoringJob | null>(detailKey, (job) =>
        job ? { ...job, deletion_requested: true } : job,
      );
      toast.success(t("messages.deleteQueued"));
      void queryClient.invalidateQueries({ queryKey: listKey });
      void queryClient.invalidateQueries({ queryKey: detailKey });
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, t("messages.deleteFailed"))),
  });
}

export function useUpdateDriftMonitoringJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateDriftMonitoringJob,
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({
        queryKey: driftQueryKeys.monitors(variables.project_id),
      });
      void queryClient.invalidateQueries({
        queryKey: driftQueryKeys.detail(variables.id),
      });
    },
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
        queryKey: driftQueryKeys.detail(variables.id),
      });
      void queryClient.invalidateQueries({
        queryKey: driftQueryKeys.monitors(variables.project_id),
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
    queryKey: [
      ...driftQueryKeys.all,
      "production-count",
      projectId ?? "",
      versionId ?? "",
    ],
    queryFn: () => getProductionDataCount(projectId!, versionId),
    enabled: Boolean(projectId),
    refetchInterval: 15000,
  });
}

export function useDeleteDriftMonitoringRun(
  monitorId?: string,
  projectId?: string,
) {
  const queryClient = useQueryClient();
  const { t } = useTranslation("monitoring");
  return useMutation({
    mutationFn: async (runId: string) => deleteDriftMonitoringRun(runId),
    onSuccess: () => {
      toast.success(t("messages.runDeleted"));
      if (monitorId) {
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.detail(monitorId),
        });
      }
      if (projectId) {
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.monitors(projectId),
        });
      }
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, t("messages.runDeleteFailed"))),
  });
}

export function useCancelDriftMonitoringRun(
  monitorId?: string,
  projectId?: string,
) {
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
    onSuccess: (_, variables) => {
      toast.success(t("messages.runCancelled"));
      const targetMonitorId = variables.monitorId ?? monitorId;
      if (targetMonitorId) {
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.detail(targetMonitorId),
        });
      }
      if (projectId) {
        void queryClient.invalidateQueries({
          queryKey: driftQueryKeys.monitors(projectId),
        });
      }
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

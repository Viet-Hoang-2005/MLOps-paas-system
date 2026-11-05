import axios from "axios";
import type { TFunction } from "i18next";
import { formatDateTime } from "@/shared/i18n/formatters";
import { formatQuotaDuration } from "./quotaFormatting";
import { getApiErrorMessage } from "@/shared/api/errors";

export function getTrainingStartError(error: unknown, t: TFunction<"training">, language: string): string {
  const body = axios.isAxiosError(error) ? error.response?.data as { error?: { code?: string; detail?: Record<string, string> } } : undefined;
  if (body?.error?.code === "training_concurrency_exceeded") return t("quotaConcurrencyError");
  if (body?.error?.code === "local_training_capacity_exceeded" && body.error.detail) {
    return t("createFlow.execution.localResourceExceeded", {
      cpu: body.error.detail.available_vcpu,
      memory: body.error.detail.available_memory_mb,
    });
  }
  if (body?.error?.code === "training_quota_exceeded" && body.error.detail) {
    const detail = body.error.detail;
    return t("quotaExceededError", {
      resource: t(`quotaProfiles.${detail.resource}`),
      required: formatQuotaDuration(Number(detail.required_seconds)),
      remaining: formatQuotaDuration(Number(detail.remaining_seconds)),
      reset: formatDateTime(detail.reset_at, language),
    });
  }
  return getApiErrorMessage(error, t("createFlow.messages.trainingStartFailed"));
}

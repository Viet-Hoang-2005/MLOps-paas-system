import { useQuery } from "@tanstack/react-query";
import { getPreview } from "@/features/projects/api/previewApi";

export const previewKeys = {
  detail: (id: string) => ["projects", "preview", id] as const,
};
export const usePreview = (id?: string) =>
  useQuery({
    queryKey: previewKeys.detail(id ?? ""),
    queryFn: () => getPreview(id!),
    enabled: Boolean(id),
  });

import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";

export async function downloadOriginal(
  path: string,
  params?: Record<string, string | number>,
): Promise<void> {
  const { data } = await apiClient.get<{ download_url: string }>(
    controlPlaneURL(path),
    { params },
  );
  const link = document.createElement("a");
  link.href = data.download_url;
  link.download = "";
  link.referrerPolicy = "no-referrer";
  document.body.append(link);
  try {
    link.click();
  } finally {
    link.remove();
  }
}

export async function downloadText(
  url: string,
  signal?: AbortSignal,
): Promise<string> {
  const response = await fetch(url, { signal });
  if (!response.ok)
    throw new Error(`File download failed (${response.status})`);
  return response.text();
}

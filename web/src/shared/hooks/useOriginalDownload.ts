import { getApiErrorMessage } from "@/shared/api/errors";
import { downloadOriginal } from "@/shared/api/files";
import { toast } from "@/shared/lib/toastStore";
import { useState } from "react";

export function useOriginalDownload(errorMessage: string) {
  const [loading, setLoading] = useState(false);

  async function download(path: string, params?: Record<string, string | number>) {
    setLoading(true);
    try {
      await downloadOriginal(path, params);
    } catch (error) {
      toast.error(getApiErrorMessage(error, errorMessage));
    } finally {
      setLoading(false);
    }
  }

  return { download, loading };
}

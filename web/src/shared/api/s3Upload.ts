import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";

/**
 * Direct-to-S3 Presigned Upload Helper
 *
 * Performs direct HTTP PUT to AWS S3 without passing through the Django backend.
 * Crucial: Does NOT attach application credentials, Authorization headers, or cookies,
 * ensuring no AWS signature mismatch or CORS credential rejection.
 */

export async function stageCsvUpload(
  purpose: "workspace" | "training-output" | "version" | "drift-monitor",
  resourceId: string,
  file: File,
  revision?: number,
): Promise<string> {
  const { data } = await apiClient.post<{
    upload_url: string;
    content_type: string;
    upload_token: string;
  }>(controlPlaneURL(`/csv-upload-urls/${purpose}/${resourceId}/`), {
    filename: file.name,
    size_bytes: file.size,
    revision,
  });
  await uploadFileToPresignedUrl(data.upload_url, file, data.content_type);
  return data.upload_token;
}

export interface UploadProgressCallback {
  (percent: number): void;
}

export function uploadFileToPresignedUrl(
  uploadUrl: string,
  file: File | Blob,
  contentType?: string,
  onProgress?: UploadProgressCallback,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl, true);

    if (contentType) {
      xhr.setRequestHeader("Content-Type", contentType);
    }

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(
          new Error(
            `Direct S3 upload failed with status ${xhr.status}: ${xhr.statusText || "Upload rejected"}`,
          ),
        );
      }
    };

    xhr.onerror = () => {
      reject(
        new Error(
          "Network error during direct S3 artifact upload. Check connection and CORS settings.",
        ),
      );
    };

    xhr.ontimeout = () => {
      reject(new Error("Direct S3 upload timed out."));
    };

    xhr.send(file);
  });
}

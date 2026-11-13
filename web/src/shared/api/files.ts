export async function downloadText(
  url: string,
  signal?: AbortSignal,
): Promise<string> {
  const response = await fetch(url, { signal });
  if (!response.ok)
    throw new Error(`File download failed (${response.status})`);
  return response.text();
}

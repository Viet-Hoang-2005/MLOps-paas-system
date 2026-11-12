export function hasDownloadableFiles(paths: string[], selected: string | null) {
  return paths.some((path) => !selected || path === selected || path.startsWith(`${selected}/`));
}

export function saveDownload({ blob, filename }: { blob: Blob; filename: string }) {
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

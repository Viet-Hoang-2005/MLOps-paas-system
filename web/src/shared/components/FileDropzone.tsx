import { UploadCloud } from "lucide-react";

export function FileDropzone({
  accept,
  title,
  subtitle,
  onChange,
}: {
  accept: string;
  title: string;
  subtitle: string;
  onChange: (file: File | null) => void;
}) {
  return (
    <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-surface border border-dashed border-border bg-muted px-4 text-center hover:border-primary">
      <UploadCloud className="mb-3 h-6 w-6 text-color-muted-foreground" />
      <span className="max-w-full truncate text-style-body-strong text-color-foreground">
        {title}
      </span>
      <span className="mt-1 text-style-caption text-color-muted-foreground">{subtitle}</span>
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
    </label>
  );
}

import { cn } from "@/shared/lib/cn";
import { UploadCloud } from "lucide-react";

export function FileDropzone({
  accept,
  title,
  subtitle,
  hint,
  onChange,
  disabled = false,
}: {
  accept: string;
  title: string;
  subtitle: string;
  hint?: string;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={cn(
        "flex min-h-40 flex-col items-center justify-center rounded-surface border border-dashed border-border bg-muted px-4 text-center transition-colors",
        disabled ? "cursor-default" : "cursor-pointer hover:border-primary",
      )}
    >
      <UploadCloud className="mb-3 h-6 w-6 text-color-muted-foreground" />
      <span className="max-w-full truncate text-style-body-strong text-color-foreground">
        {title}
      </span>
      <span className="mt-1 text-style-caption text-color-muted-foreground">
        {subtitle}
      </span>
      {hint && (
        <span className="mt-0.5 text-style-caption text-color-muted-foreground">
          {hint}
        </span>
      )}
      <input
        type="file"
        accept={accept}
        disabled={disabled}
        className="hidden"
        onChange={(event) => {
          if (!disabled) {
            onChange(event.target.files?.[0] ?? null);
          }
        }}
      />
    </label>
  );
}

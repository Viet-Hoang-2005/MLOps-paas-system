import { Button } from "@/shared/components/Button";
import { cn } from "@/shared/lib/cn";
import { UploadCloud, X } from "lucide-react";
import { useRef, useState, type MouseEvent, type ChangeEvent } from "react";

export interface FileDropzoneProps {
  accept: string;
  title: string;
  subtitle: string;
  hint?: string;
  onChange: (file: File | null) => void;
  onRemove?: () => void;
  hasFile?: boolean;
  removeTitle?: string;
  disabled?: boolean;
  className?: string;
}

export function FileDropzone({
  accept,
  title,
  subtitle,
  hint,
  onChange,
  onRemove,
  hasFile,
  removeTitle = "Remove file",
  disabled = false,
  className,
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [internalHasFile, setInternalHasFile] = useState(false);

  const isFilePresent = hasFile !== undefined ? hasFile : internalHasFile;

  const handleRemove = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    setInternalHasFile(false);
    if (onRemove) {
      onRemove();
    } else {
      onChange(null);
    }
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (disabled) return;
    const file = event.target.files?.[0] ?? null;
    setInternalHasFile(Boolean(file));
    onChange(file);
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      className={cn(
        "relative flex min-h-40 flex-col items-center justify-center rounded-surface border border-dashed border-border bg-muted px-4 text-center transition-colors",
        disabled
          ? "cursor-default"
          : "cursor-pointer hover:border-primary [&:has(button:hover)]:border-border [&:has(button:hover)]:cursor-default",
        className,
      )}
      onClick={(event) => {
        if (disabled) return;
        if ((event.target as HTMLElement).closest("button")) return;
        inputRef.current?.click();
      }}
      onKeyDown={(event) => {
        if (disabled) return;
        if (event.key === "Enter" || event.key === " ") {
          if ((event.target as HTMLElement).closest("button")) return;
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      {isFilePresent && !disabled && (
        <Button
          type="button"
          size="icon"
          variant="secondary"
          border={false}
          icon={<X className="h-4 w-4" />}
          onClick={handleRemove}
          title={removeTitle}
          aria-label={removeTitle}
          className="absolute top-2.5 right-2.5 z-10 h-7 w-7 p-0 hover:bg-transparent hover:border-transparent active:bg-transparent"
        />
      )}

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
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        tabIndex={-1}
        className="hidden"
        onChange={handleInputChange}
      />
    </div>
  );
}

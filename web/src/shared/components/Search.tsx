import {
  forwardRef,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type ChangeEvent,
  type InputHTMLAttributes,
  type KeyboardEvent,
} from "react";
import { Search as SearchIcon, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/shared/lib/cn";

export interface SearchProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  wrapperClassName?: string;
  onClear?: () => void;
  clearAriaLabel?: string;
  type?: string;
}

export const Search = forwardRef<HTMLInputElement, SearchProps>(function Search(
  {
    value,
    defaultValue,
    onChange,
    onClear,
    onKeyDown,
    clearAriaLabel,
    placeholder,
    className,
    wrapperClassName,
    disabled,
    id,
    type = "text",
    ...props
  },
  forwardedRef,
) {
  const { t } = useTranslation("common");
  const generatedId = useId();
  const inputId = id || generatedId;
  const inputRef = useRef<HTMLInputElement | null>(null);

  useImperativeHandle(forwardedRef, () => inputRef.current as HTMLInputElement);

  const [internalValue, setInternalValue] = useState(defaultValue ?? "");
  const isControlled = value !== undefined;
  const currentValue = isControlled
    ? String(value ?? "")
    : String(internalValue ?? "");
  const hasValue = currentValue.length > 0;

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (!isControlled) {
      setInternalValue(event.target.value);
    }
    onChange?.(event);
  };

  const handleClear = () => {
    if (!isControlled) {
      setInternalValue("");
    }
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    onClear?.();
    if (onChange && inputRef.current) {
      const target = inputRef.current;
      target.value = "";
      const syntheticEvent = {
        target,
        currentTarget: target,
      } as ChangeEvent<HTMLInputElement>;
      onChange(syntheticEvent);
    }
    inputRef.current?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape" && hasValue) {
      event.stopPropagation();
      handleClear();
    }
    onKeyDown?.(event);
  };

  return (
    <div className={cn("relative w-full", wrapperClassName)}>
      <SearchIcon
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-color-muted-foreground"
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        id={inputId}
        type={type}
        role="searchbox"
        value={value}
        defaultValue={defaultValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder ?? t("actions.search")}
        className={cn(
          "h-10 w-full rounded-surface border border-input bg-surface pl-9 pr-9 text-style-body text-color-foreground outline-none transition-colors placeholder:text-color-muted-foreground focus:border-primary disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-disabled disabled:text-color-foreground-disabled",
          className,
        )}
        {...props}
      />
      {hasValue && !disabled && (
        <button
          type="button"
          onClick={handleClear}
          className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-compact text-color-muted-foreground transition-colors hover:bg-muted hover:text-color-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label={clearAriaLabel || t("actions.clear")}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
});

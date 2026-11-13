import {
  forwardRef,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type ChangeEvent,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Search as SearchIcon, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/shared/lib/cn";

export interface SearchSuggestion {
  value: string;
  label: string;
  description?: ReactNode;
}

export interface SearchProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type"
> {
  wrapperClassName?: string;
  onClear?: () => void;
  clearAriaLabel?: string;
  type?: string;
  suggestions?: SearchSuggestion[];
  onSuggestionSelect?: (value: string) => void;
  suggestionsEmptyMessage?: ReactNode;
  suggestionsFooter?: ReactNode;
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
    suggestions,
    onSuggestionSelect,
    suggestionsEmptyMessage,
    suggestionsFooter,
    onFocus,
    onBlur,
    onClick,
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
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const visibleSuggestions =
    suggestions?.filter((item) =>
      item.label
        .toLocaleLowerCase()
        .includes(currentValue.trim().toLocaleLowerCase()),
    ) ?? [];
  const expanded = open && suggestions !== undefined && !disabled;
  const listId = `${inputId}-suggestions`;
  const choose = (suggestion: SearchSuggestion) => {
    setOpen(false);
    setActiveIndex(-1);
    onSuggestionSelect?.(suggestion.value);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (!isControlled) {
      setInternalValue(event.target.value);
    }
    onChange?.(event);
    setOpen(true);
    setActiveIndex(-1);
  };

  const handleClear = () => {
    setOpen(true);
    setActiveIndex(-1);
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
    onKeyDown?.(event);
    if (event.defaultPrevented) return;
    if (
      suggestions !== undefined &&
      (event.key === "ArrowDown" || event.key === "ArrowUp")
    ) {
      event.preventDefault();
      setOpen(true);
      const next = visibleSuggestions.length
        ? activeIndex < 0 || !expanded
          ? event.key === "ArrowDown"
            ? 0
            : visibleSuggestions.length - 1
          : (activeIndex +
              (event.key === "ArrowDown" ? 1 : -1) +
              visibleSuggestions.length) %
            visibleSuggestions.length
        : -1;
      setActiveIndex(next);
      if (next >= 0)
        document
          .getElementById(`${listId}-${next}`)
          ?.scrollIntoView?.({ block: "nearest" });
    } else if (
      event.key === "Enter" &&
      expanded &&
      visibleSuggestions[activeIndex]
    ) {
      event.preventDefault();
      choose(visibleSuggestions[activeIndex]);
    } else if (event.key === "Escape" && expanded) {
      event.stopPropagation();
      setOpen(false);
      setActiveIndex(-1);
    } else if (event.key === "Escape" && hasValue) {
      event.stopPropagation();
      handleClear();
    }
  };

  return (
    <div
      className={cn("relative w-full", wrapperClassName)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <SearchIcon
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-color-muted-foreground"
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        id={inputId}
        type={type}
        role={suggestions === undefined ? "searchbox" : "combobox"}
        aria-expanded={suggestions === undefined ? undefined : expanded}
        aria-controls={expanded ? listId : undefined}
        aria-autocomplete={suggestions === undefined ? undefined : "list"}
        aria-activedescendant={
          expanded && visibleSuggestions[activeIndex]
            ? `${listId}-${activeIndex}`
            : undefined
        }
        value={value}
        defaultValue={defaultValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={(event) => {
          setOpen(true);
          onFocus?.(event);
        }}
        onBlur={onBlur}
        onClick={(event) => {
          setOpen(true);
          onClick?.(event);
        }}
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
      {expanded && (
        <div className="absolute left-0 top-full z-50 mt-2 w-full rounded-surface border border-border bg-surface p-1 shadow-(--shadow-overlay)">
          <div
            id={listId}
            role="listbox"
            aria-label={
              props["aria-label"] ?? placeholder ?? t("actions.search")
            }
            className="flex flex-col max-h-[min(18rem,50vh)] overflow-y-auto"
          >
            {visibleSuggestions.map((item, index) => (
              <div
                key={item.value}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={activeIndex === index}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(item)}
                className={cn(
                  "flex items-center justify-between gap-3 cursor-pointer rounded-compact px-3 py-2",
                  activeIndex === index && "bg-muted",
                )}
              >
                <span className="min-w-0 truncate text-style-body-strong">
                  {item.label}
                </span>
                {item.description && (
                  <span
                    className={cn(
                      "shrink-0",
                      typeof item.description === "string" &&
                        "truncate text-style-caption text-color-muted-foreground",
                    )}
                  >
                    {item.description}
                  </span>
                )}
              </div>
            ))}
          </div>
          {!visibleSuggestions.length && (
            <p
              role="status"
              className="px-3 py-6 text-style-body text-color-muted-foreground"
            >
              {suggestionsEmptyMessage}
            </p>
          )}
          {suggestionsFooter && (
            <div
              className="mt-1 border-t border-border pt-1"
              onClick={() => setOpen(false)}
            >
              {suggestionsFooter}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

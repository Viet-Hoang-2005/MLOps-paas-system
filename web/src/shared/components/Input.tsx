import {
  forwardRef,
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { cn } from "@/shared/lib/cn";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/shared/components/Button";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: ReactNode;
  rightElement?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, helperText, icon, rightElement, className, id, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const messageId = `${inputId}-message`;
  return (
    <div className="flex w-full flex-col gap-2">
      {label && (
        <label
          htmlFor={inputId}
          className="text-style-body-strong text-color-foreground"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-color-foreground-subtle"
            aria-hidden="true"
          >
            {icon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={error || helperText ? messageId : undefined}
          className={cn(
            `h-14 w-full px-4 rounded-control
            border border-input bg-surface
            text-style-body text-color-foreground outline-none transition-colors
            placeholder:text-color-foreground-subtle hover:border-input-hover focus:border-input-hover
            disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-disabled disabled:text-color-foreground-disabled
            disabled:hover:border-border`,
            icon && "pl-11",
            rightElement && "pr-12",
            error &&
              "border-danger hover:border-danger focus:border-danger focus:ring-danger/15",
            className,
          )}
          {...props}
        />
        {rightElement && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center">
            {rightElement}
          </div>
        )}
      </div>
      {(error || helperText) && (
        <span
          id={messageId}
          role={error ? "alert" : undefined}
          className={cn(
            "text-style-caption",
            error ? "text-color-danger" : "text-color-foreground-subtle",
          )}
        >
          {error || helperText}
        </span>
      )}
    </div>
  );
});

export const InputPassword = forwardRef<HTMLInputElement, InputProps>(
  function InputPassword({ className, ...props }, ref) {
    const [showPassword, setShowPassword] = useState(false);
    const { t } = useTranslation("common");

    const togglePasswordVisibility = () => {
      setShowPassword((prev) => !prev);
    };

    const actionLabel = showPassword
      ? t("accessibility.hidePassword")
      : t("accessibility.showPassword");

    const toggleButton = (
      <Button
        size="icon"
        variant="secondary"
        border={false}
        onClick={togglePasswordVisibility}
        aria-label={actionLabel}
        title={actionLabel}
        icon={
          showPassword ? (
            <EyeOff className="h-5 w-5" />
          ) : (
            <Eye className="h-5 w-5" />
          )
        }
      />
    );

    return (
      <Input
        ref={ref}
        type={showPassword ? "text" : "password"}
        rightElement={toggleButton}
        className={className}
        {...props}
      />
    );
  },
);

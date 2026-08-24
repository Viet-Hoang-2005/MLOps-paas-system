import type { ComponentProps } from "react";
import { useTheme } from "@/app/theme/useTheme";
import GitHubIcon from "@/assets/icons/GitHub.png";
import GitHubDarkIcon from "@/assets/icons/GitHub-Dark.png";
import GoogleIcon from "@/assets/icons/Google.png";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/components/Button";

export type OAuthProvider = "google" | "github";

interface OAuthButtonProps
  extends Omit<ComponentProps<typeof Button>, "children" | "icon"> {
  provider: OAuthProvider;
  label: string;
}

export function OAuthButton({
  provider,
  label,
  className,
  ...props
}: OAuthButtonProps) {
  const { resolvedTheme } = useTheme();
  const icon =
    provider === "google"
      ? GoogleIcon
      : resolvedTheme === "dark"
        ? GitHubDarkIcon
        : GitHubIcon;

  return (
    <Button
      variant="outline"
      size="lg"
      className={cn(
        "flex-1 hover:border-input-hover hover:bg-transparent active:border-primary-active active:bg-transparent",
        className,
      )}
      icon={
        <img
          src={icon}
          alt=""
          aria-hidden="true"
          className="h-5 w-5"
        />
      }
      data-oauth-provider={provider}
      {...props}
    >
      {label}
    </Button>
  );
}

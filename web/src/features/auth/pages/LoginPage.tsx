import { useGoogleLogin } from "@react-oauth/google";
import { Mail, LockKeyhole } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { OAuthButton } from "@/features/auth/components/OAuthButton";
import { Button } from "@/shared/components/Button";
import { Divider } from "@/features/auth/components/Divider";
import { Input, InputPassword } from "@/shared/components/Input";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { startGitHubOAuth } from "@/features/auth/lib/oauth";
import { toast } from "@/shared/components/toastStore";
import { useForm } from "@/features/auth/hooks/useForm";
import MLdriftLogo from "@/assets/icons/MLdrift.png";

export default function LoginPage() {
  const { t } = useTranslation("auth");
  const { login, loginWithGoogle, loading } = useAuth();
  const { values, updateField } = useForm({ email: "", password: "" });
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
  const openGoogleLogin = useGoogleLogin({
    scope: "openid email profile",
    onSuccess: (tokenResponse) => {
      void loginWithGoogle(tokenResponse.access_token);
    },
    onError: () => toast.error(t("login.googleFailed")),
  });

  const handleGoogleLogin = () => {
    if (!googleClientId) {
      toast.error(t("login.googleMissing"));
      return;
    }
    openGoogleLogin();
  };

  const handleGitHubLogin = () => {
    try {
      startGitHubOAuth();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("login.githubMissing"),
      );
    }
  };

  return (
    <AuthCard>
      <div className="rounded-surface flex items-center justify-center mx-auto mb-2">
        <img src={MLdriftLogo} alt="MLdrift" className="w-8 h-8" />
      </div>

      <h2 className="mb-1 text-center text-style-page-title font-bold text-color-foreground">
        {t("login.title")}
      </h2>
      <p className="mb-8 text-center text-style-body text-color-muted-foreground">
        {t("login.description")}
      </p>

      <div className="flex gap-3 mb-6">
        <OAuthButton
          provider="google"
          label={t("login.google")}
          id="btn-google-login"
          onClick={handleGoogleLogin}
        />
        <OAuthButton
          provider="github"
          label={t("login.github")}
          id="btn-github-login"
          onClick={handleGitHubLogin}
        />
      </div>

      <div className="mb-6">
        <Divider label={t("login.divider")} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          login(values);
        }}
        className="flex flex-col gap-4"
      >
        <Input
          id="input-email"
          name="email"
          autoComplete="email"
          label={t("login.email")}
          type="email"
          placeholder={t("login.emailPlaceholder")}
          icon={<Mail className="w-4 h-4" />}
          value={values.email}
          onChange={(e) => updateField("email", e.target.value)}
        />

        <InputPassword
          id="input-password"
          name="password"
          autoComplete="current-password"
          label={t("login.password")}
          placeholder={t("login.passwordPlaceholder")}
          icon={<LockKeyhole className="w-4 h-4" />}
          value={values.password}
          onChange={(e) => updateField("password", e.target.value)}
        />

        <div className="flex justify-end">
          <Link
            to="/forgot-password"
            className="text-style-caption-strong text-color-foreground underline hover:text-color-primary-hover"
          >
            {t("login.forgotPassword")}
          </Link>
        </div>

        <Button
          id="btn-login"
          type="submit"
          variant="primary"
          fullWidth
          loading={loading}
          className="mt-2 "
        >
          {t("login.submit")}
        </Button>
      </form>

      <p className="mt-8 text-center text-style-body text-color-muted-foreground">
        {t("login.noAccount")}{" "}
        <Link
          to="/signup"
          className="font-semibold text-color-foreground underline hover:text-color-primary-hover"
        >
          {t("login.signUp")}
        </Link>
      </p>
    </AuthCard>
  );
}

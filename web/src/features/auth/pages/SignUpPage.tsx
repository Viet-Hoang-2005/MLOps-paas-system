import { useGoogleLogin } from "@react-oauth/google";
import { Mail, UserPlus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { OAuthButton } from "@/features/auth/components/OAuthButton";
import { Button } from "@/shared/components/Button";
import { Divider } from "@/features/auth/components/Divider";
import { Input } from "@/shared/components/Input";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { requestOTP } from "@/features/auth/api/authApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { startGitHubOAuth } from "@/features/auth/lib/oauth";
import { toast } from "@/shared/components/toastStore";

export default function SignUpPage() {
  const navigate = useNavigate();
  const { t } = useTranslation("auth");
  const { loginWithGoogle } = useAuth();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
  const openGoogleLogin = useGoogleLogin({
    scope: "openid email profile",
    onSuccess: (tokenResponse) => {
      void loginWithGoogle(tokenResponse.access_token);
    },
    onError: () => toast.error(t("signup.googleFailed")),
  });

  const handleGoogleSignUp = () => {
    if (!googleClientId) {
      toast.error(t("login.googleMissing"));
      return;
    }
    openGoogleLogin();
  };

  const handleRequestOTP = async () => {
    if (!email) {
      toast.warning(t("signup.emailRequired"));
      return;
    }

    setLoading(true);
    try {
      await requestOTP({ email });
      toast.success(t("signup.otpSent"));
      navigate("/signup/verify-otp", { state: { email } });
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("signup.otpFailed")));
    } finally {
      setLoading(false);
    }
  };

  const handleGitHubSignUp = () => {
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
      <div className="mb-2 rounded-surface flex items-center justify-center mx-auto">
        <UserPlus className="h-8 w-8 text-color-foreground" />
      </div>

      <h2 className="mb-1 text-center text-style-page-title font-bold text-color-foreground">
        {t("signup.title")}
      </h2>
      <p className="mb-8 text-center text-style-body text-color-muted-foreground">
        {t("signup.description")}
      </p>

      <div className="flex gap-3 mb-6">
        <OAuthButton
          provider="google"
          label={t("login.google")}
          id="btn-google-signup"
          onClick={handleGoogleSignUp}
        />
        <OAuthButton
          provider="github"
          label={t("login.github")}
          id="btn-github-signup"
          onClick={handleGitHubSignUp}
        />
      </div>

      <div className="mb-6">
        <Divider label={t("signup.divider")} />
      </div>

      <div className="flex flex-col gap-4">
        <Input
          id="input-signup-email"
          name="email"
          autoComplete="email"
          label={t("login.email")}
          type="email"
          placeholder={t("login.emailPlaceholder")}
          icon={<Mail className="w-4 h-4" />}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleRequestOTP()}
        />

        <Button
          id="btn-signup"
          variant="primary"
          fullWidth
          loading={loading}
          onClick={handleRequestOTP}
          className="mt-4"
        >
          {t("signup.submit")}
        </Button>
      </div>

      <p className="mt-8 text-center text-style-body text-color-muted-foreground">
        {t("signup.hasAccount")}{" "}
        <Link
          to="/login"
          className="font-semibold text-color-foreground underline hover:text-color-primary-hover"
        >
          {t("signup.signIn")}
        </Link>
      </p>
    </AuthCard>
  );
}

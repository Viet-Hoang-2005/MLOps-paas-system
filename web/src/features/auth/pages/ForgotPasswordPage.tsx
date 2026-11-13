import {
  forgotPasswordOTP,
  resetForgottenPassword,
  verifyForgotPasswordOTP,
} from "@/features/auth/api/authApi";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { useCountdown } from "@/features/auth/hooks/useCountdown";
import { useForm } from "@/features/auth/hooks/useForm";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Back } from "@/shared/components/Back";
import { Button } from "@/shared/components/Button";
import { Input, InputPassword } from "@/shared/components/Input";
import { OTPInput } from "@/shared/components/OTPInput";
import { toast } from "@/shared/lib/toastStore";
import { LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

type ForgotPasswordStep = "email" | "otp" | "reset";

interface ForgotPasswordOTPStepProps {
  email: string;
  onVerified: (resetToken: string) => void;
  onBack: () => void;
}

function ForgotPasswordOTPStep({
  email,
  onVerified,
  onBack,
}: ForgotPasswordOTPStepProps) {
  const { t } = useTranslation("auth");
  const { seconds, isRunning, reset: resetCountdown } = useCountdown(60);
  const [otpValue, setOtpValue] = useState("");
  const [loading, setLoading] = useState(false);

  const handleVerify = async (otp?: string) => {
    const code = otp || otpValue;
    if (code.length !== 6) {
      toast.warning(t("otp.invalid"));
      return;
    }

    setLoading(true);
    try {
      const response = await verifyForgotPasswordOTP(email, code);
      toast.success(t("recovery.verified"));
      onVerified(response.reset_token);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("otp.expired")));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    try {
      await forgotPasswordOTP(email);
      toast.success(t("otp.resent"));
      resetCountdown();
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("otp.resendFailed")));
    }
  };

  const handleOTPComplete = (otp: string) => {
    setOtpValue(otp);
    void handleVerify(otp);
  };

  return (
    <div className="max-w-sm w-full mx-auto text-center">
      <Back onBack={onBack} title={t("otp.back")} className="mb-8" />

      <div className="mx-auto mb-4 rounded-surface flex items-center justify-center">
        <Mail className="h-8 w-8 text-color-foreground" />
      </div>

      <h2 className="mb-2 text-style-page-title font-bold text-color-foreground">
        {t("otp.title")}
      </h2>
      <p className="mb-8 text-style-body text-color-muted-foreground">
        {t("otp.description", { email })}
      </p>

      <div className="mb-6">
        <OTPInput onComplete={handleOTPComplete} disabled={loading} />
      </div>

      <Button
        id="btn-verify-reset-otp"
        variant="primary"
        fullWidth
        loading={loading}
        onClick={() => void handleVerify()}
      >
        {t("otp.verify")}
      </Button>

      <p className="mt-6 text-style-body text-color-muted-foreground">
        {t("otp.missing")}{" "}
        {isRunning ? (
          <span className="font-semibold text-color-muted-foreground">
            {t("otp.resendIn", { seconds })}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void handleResend()}
            className="cursor-pointer font-semibold text-color-foreground hover:opacity-60"
          >
            {t("otp.resend")}
          </button>
        )}
      </p>
    </div>
  );
}

interface ForgotPasswordResetStepProps {
  email: string;
  resetToken: string;
  onBack: () => void;
}

function ForgotPasswordResetStep({
  email,
  resetToken,
  onBack,
}: ForgotPasswordResetStepProps) {
  const { t } = useTranslation("auth");
  const navigate = useNavigate();

  const { values, errors, loading, updateField, handleSubmit } = useForm(
    { password: "", confirmPassword: "" },
    {
      password: (value: string) =>
        !value
          ? t("profile.passwordRequired")
          : value.length < 8
            ? t("profile.passwordLength")
            : undefined,
      confirmPassword: (value: string, all: Record<string, string>) =>
        value !== all.password ? t("profile.mismatch") : undefined,
    },
  );

  const onSubmit = handleSubmit(async (formValues) => {
    try {
      await resetForgottenPassword(resetToken, formValues.password);
      toast.success(t("recovery.resetSuccess"));
      navigate("/login", { replace: true });
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("recovery.resetFailed")));
    }
  });

  return (
    <div className="max-w-sm w-full mx-auto">
      <Back onBack={onBack} title={t("recovery.startOver")} className="mb-8" />

      <div className="mb-4 rounded-surface flex items-center justify-center mx-auto">
        <LockKeyhole className="h-8 w-8 text-color-foreground" />
      </div>

      <h2 className="mb-2 text-center text-style-page-title font-bold text-color-foreground">
        {t("recovery.newTitle")}
      </h2>
      <p className="mb-8 text-center text-style-body text-color-muted-foreground">
        {t("recovery.newDescription", { email })}
      </p>

      <div className="flex flex-col gap-4">
        <InputPassword
          id="input-reset-password"
          name="new-password"
          autoComplete="new-password"
          label={t("recovery.newPassword")}
          placeholder={t("recovery.passwordPlaceholder")}
          value={values.password}
          error={errors.password}
          onChange={(event) => updateField("password", event.target.value)}
        />
        <InputPassword
          id="input-confirm-reset-password"
          name="confirm-password"
          autoComplete="new-password"
          label={t("recovery.confirmPassword")}
          placeholder={t("recovery.confirmPlaceholder")}
          value={values.confirmPassword}
          error={errors.confirmPassword}
          onChange={(event) =>
            updateField("confirmPassword", event.target.value)
          }
          onKeyDown={(event) => event.key === "Enter" && void onSubmit()}
        />
        <Button
          id="btn-reset-password"
          variant="primary"
          fullWidth
          loading={loading}
          onClick={onSubmit}
          className="mt-4"
        >
          {t("recovery.reset")}
        </Button>
      </div>
    </div>
  );
}

export default function ForgotPasswordPage() {
  const { t } = useTranslation("auth");
  const [step, setStep] = useState<ForgotPasswordStep>("email");
  const [email, setEmail] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSendOTP = async () => {
    if (!email) {
      toast.warning(t("signup.emailRequired"));
      return;
    }
    setLoading(true);
    try {
      const response = await forgotPasswordOTP(email);
      toast.success(t("signup.otpSent"));
      setEmail(response.email || email.trim().toLowerCase());
      setStep("otp");
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("recovery.sendFailed")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard>
      {step === "email" && (
        <div className="max-w-sm w-full mx-auto">
          {/* Back to Login */}
          <Back
            to="/login"
            title={t("recovery.backToSignIn")}
            className="mb-8"
          />

          {/* Icon */}
          <div className="mb-4 rounded-surface flex items-center justify-center mx-auto">
            <Mail className="h-8 w-8 text-color-foreground" />
          </div>

          <h2 className="mb-2 text-center text-style-page-title font-bold text-color-foreground">
            {t("recovery.title")}
          </h2>
          <p className="mb-6 text-center text-style-body text-color-muted-foreground">
            {t("recovery.description")}
          </p>

          <div className="flex flex-col gap-4">
            <Input
              id="input-forgot-email"
              name="email"
              autoComplete="email"
              label={t("login.email")}
              type="email"
              placeholder={t("login.emailPlaceholder")}
              icon={<Mail className="h-4 w-4" />}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void handleSendOTP()}
            />
            <Button
              id="btn-send-otp"
              variant="primary"
              fullWidth
              loading={loading}
              onClick={() => void handleSendOTP()}
              className="mt-4"
            >
              {t("recovery.send")}
            </Button>
          </div>
        </div>
      )}

      {step === "otp" && (
        <ForgotPasswordOTPStep
          email={email}
          onVerified={(token) => {
            setResetToken(token);
            setStep("reset");
          }}
          onBack={() => setStep("email")}
        />
      )}

      {step === "reset" && (
        <ForgotPasswordResetStep
          email={email}
          resetToken={resetToken}
          onBack={() => setStep("email")}
        />
      )}
    </AuthCard>
  );
}

import {
  completeRegistration,
  requestOTP,
  verifyOTP,
} from "@/features/auth/api/authApi";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { Divider } from "@/features/auth/components/Divider";
import { OAuthButton } from "@/features/auth/components/OAuthButton";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { useCountdown } from "@/features/auth/hooks/useCountdown";
import { useForm } from "@/features/auth/hooks/useForm";
import { startGitHubOAuth } from "@/features/auth/lib/oauth";
import { AvatarDialog } from "@/shared/components/AvatarDialog";
import { CropDialog } from "@/shared/components/CropDialog";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Back } from "@/shared/components/Back";
import { Button } from "@/shared/components/Button";
import { Input, InputPassword } from "@/shared/components/Input";
import { OTPInput } from "@/shared/components/OTPInput";
import { toast } from "@/shared/lib/toastStore";
import { useGoogleLogin } from "@react-oauth/google";
import {
  Camera,
  Lock,
  LockKeyhole,
  Mail,
  User,
  UserPlus,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

type SignUpStep = "email" | "otp" | "profile";
type AvatarModalState = "closed" | "options";

interface SignUpOTPStepProps {
  email: string;
  onVerified: (registrationToken: string) => void;
  onBack: () => void;
}

function SignUpOTPStep({ email, onVerified, onBack }: SignUpOTPStepProps) {
  const { t } = useTranslation("auth");
  const { seconds, isRunning, reset: resetCountdown } = useCountdown(60);
  const [loading, setLoading] = useState(false);
  const [otpValue, setOtpValue] = useState("");

  const handleVerify = async (otp?: string) => {
    const code = otp || otpValue;
    if (code.length !== 6) {
      toast.warning(t("otp.invalid"));
      return;
    }
    setLoading(true);
    try {
      const response = await verifyOTP({ email, otp_code: code });
      toast.success(t("otp.verified"));
      onVerified(response.registration_token);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("otp.expired")));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    try {
      await requestOTP({ email });
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
    <div className="flex flex-col max-w-sm w-full mx-auto text-center gap-8">
      <Back
        onBack={onBack}
        title={t("otp.back")}
      />

      <div className="flex flex-col items-center justify-center gap-3">
        <Mail className="h-8 w-8 text-color-foreground" />
        <h2 className="text-style-page-title font-bold text-color-foreground">
          {t("otp.title")}
        </h2>
        <p className="text-style-body text-color-muted-foreground">
          {t("otp.description", { email })}
        </p>
      </div>

      <OTPInput onComplete={handleOTPComplete} disabled={loading} />

      <Button
        id="btn-verify-otp"
        variant="primary"
        fullWidth
        loading={loading}
        onClick={() => void handleVerify()}
      >
        {t("otp.verify")}
      </Button>

      <p className="text-style-body text-color-muted-foreground">
        {t("otp.missing")}{" "}
        {isRunning ? (
          <span className="font-semibold text-color-muted-foreground">
            {t("otp.resendIn", { seconds })}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void handleResend()}
            className="cursor-pointer font-semibold text-color-foreground hover:text-color-primary-hover"
          >
            {t("otp.resend")}
          </button>
        )}
      </p>
    </div>
  );
}

interface SignUpProfileStepProps {
  email: string;
  registrationToken: string;
  onBack: () => void;
}

function SignUpProfileStep({
  email,
  registrationToken,
  onBack,
}: SignUpProfileStepProps) {
  const { t } = useTranslation("auth");
  const { saveAuthTokens } = useAuth();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState("");
  const [cropImage, setCropImage] = useState("");
  const [avatarModal, setAvatarModal] = useState<AvatarModalState>("closed");

  const { values, errors, loading, updateField, handleSubmit } = useForm(
    { full_name: "", password: "", confirmPassword: "" },
    {
      full_name: (value: string) =>
        !value ? t("profile.fullNameRequired") : undefined,
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

  useEffect(() => {
    return () => {
      if (avatarPreview) URL.revokeObjectURL(avatarPreview);
      if (cropImage) URL.revokeObjectURL(cropImage);
    };
  }, [avatarPreview, cropImage]);

  const handleAvatarSelection = (file?: File) => {
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast.warning(t("profile.imageOnly"));
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast.warning(t("profile.imageSize"));
      return;
    }

    if (cropImage) URL.revokeObjectURL(cropImage);
    const nextCropImage = URL.createObjectURL(file);
    setAvatarModal("closed");
    setCropImage(nextCropImage);
  };

  const closeCropModal = () => {
    if (cropImage) URL.revokeObjectURL(cropImage);
    setCropImage("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const confirmAvatarCrop = (croppedFile: File) => {
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    setAvatarFile(croppedFile);
    setAvatarPreview(URL.createObjectURL(croppedFile));
    closeCropModal();
  };

  const openAvatarModal = () => {
    setAvatarModal("options");
  };

  const openAvatarPicker = () => {
    fileInputRef.current?.click();
  };

  const removeAvatar = () => {
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    setAvatarFile(null);
    setAvatarPreview("");
    setAvatarModal("closed");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const onSubmit = handleSubmit(async (v) => {
    try {
      const response = await completeRegistration({
        registration_token: registrationToken,
        full_name: v.full_name,
        password: v.password,
        avatar: avatarFile,
      });
      toast.success(t("profile.success"));
      saveAuthTokens(response.access, "/dashboard", response.tenant_id);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("profile.failed")));
    }
  });

  return (
    <div className="max-w-sm w-full mx-auto">
      <Back
        onBack={onBack}
        title={t("profile.back")}
        className="mb-4"
      />

      <h2 className="mb-1 text-style-page-title font-bold text-color-foreground">
        {t("profile.title")}
      </h2>
      <p className="mb-6 text-style-body text-color-muted-foreground">
        {t("profile.registering", { email })}
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="flex flex-col gap-4"
      >
        <button
          type="button"
          onClick={openAvatarModal}
          aria-label={t("profile.setAvatar")}
          title={t("profile.setAvatar")}
          className="flex w-full items-center justify-between gap-4 rounded-control border border-border bg-surface px-4 py-3 text-left transition-colors hover:border-primary focus:border-primary focus:outline-none"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-color-muted-foreground">
              {avatarPreview ? (
                <img
                  src={avatarPreview}
                  alt={t("profile.avatarPreview")}
                  className="h-full w-full object-cover"
                />
              ) : (
                <Camera className="h-5 w-5" />
              )}
            </div>
            <div>
              <p className="text-style-body-strong text-color-foreground">
                {t("profile.avatar")}
              </p>
              <p className="text-style-caption text-color-muted-foreground">
                {t("profile.avatarDescription")}
              </p>
            </div>
          </div>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(event) => handleAvatarSelection(event.target.files?.[0])}
        />

        <Input
          id="input-fullname"
          name="full_name"
          autoComplete="name"
          label={t("profile.fullName")}
          placeholder={t("profile.fullNamePlaceholder")}
          icon={<User className="h-4 w-4" />}
          value={values.full_name}
          error={errors.full_name}
          onChange={(e) => updateField("full_name", e.target.value)}
        />
        <InputPassword
          id="input-new-password"
          name="new-password"
          autoComplete="new-password"
          label={t("profile.password")}
          placeholder={t("profile.passwordPlaceholder")}
          icon={<Lock className="h-4 w-4" />}
          value={values.password}
          error={errors.password}
          onChange={(e) => updateField("password", e.target.value)}
        />
        <InputPassword
          id="input-confirm-password"
          name="confirm-password"
          autoComplete="new-password"
          label={t("profile.confirm")}
          placeholder={t("profile.confirmPlaceholder")}
          icon={<LockKeyhole className="h-4 w-4" />}
          value={values.confirmPassword}
          error={errors.confirmPassword}
          onChange={(e) => updateField("confirmPassword", e.target.value)}
        />

        <Button
          id="btn-create-account"
          type="submit"
          variant="primary"
          fullWidth
          loading={loading}
          className="mt-6"
        >
          {t("profile.submit")}
        </Button>
      </form>

      <AvatarDialog
        open={avatarModal === "options"}
        avatarPreview={avatarPreview}
        onClose={() => setAvatarModal("closed")}
        onRemove={removeAvatar}
        onChange={openAvatarPicker}
      />

      <CropDialog
        imageSrc={cropImage}
        onClose={closeCropModal}
        onConfirm={confirmAvatarCrop}
        onError={() => toast.error(t("profile.cropFailed"))}
      />
    </div>
  );
}

export default function SignUpPage() {
  const { t } = useTranslation("auth");
  const { loginWithGoogle } = useAuth();
  const [step, setStep] = useState<SignUpStep>("email");
  const [email, setEmail] = useState("");
  const [registrationToken, setRegistrationToken] = useState("");
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
      setStep("otp");
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
      {step === "email" && (
        <>
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
              onKeyDown={(e) => e.key === "Enter" && void handleRequestOTP()}
            />

            <Button
              id="btn-signup"
              variant="primary"
              fullWidth
              loading={loading}
              onClick={() => void handleRequestOTP()}
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
        </>
      )}

      {step === "otp" && (
        <SignUpOTPStep
          email={email}
          onVerified={(token) => {
            setRegistrationToken(token);
            setStep("profile");
          }}
          onBack={() => setStep("email")}
        />
      )}

      {step === "profile" && (
        <SignUpProfileStep
          email={email}
          registrationToken={registrationToken}
          onBack={() => setStep("email")}
        />
      )}
    </AuthCard>
  );
}

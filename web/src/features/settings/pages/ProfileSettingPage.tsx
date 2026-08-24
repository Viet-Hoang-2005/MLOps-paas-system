import {
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  Camera,
  ChevronDown,
  FileText,
  Fingerprint,
  Globe2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Tags,
  Trash2,
  UserRound,
  Edit3,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { AvatarCropModal } from "@/features/settings/components/AvatarCropModal";
import { AvatarModal } from "@/features/settings/components/AvatarModal";
import { Button } from "@/shared/components/Button";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { Input, InputPassword } from "@/shared/components/Input";
import { OTPInput } from "@/shared/components/OTPInput";
import { useProfileSettings } from "@/features/settings/hooks/useProfileSettings";
import { toast } from "@/shared/components/toastStore";
import type { UserProfile } from "@/features/settings/types";
import BaseModal from "@/shared/components/BaseModal";

const formatDate = (value: string | undefined, fallback: string) => {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

const getInitials = (profile: UserProfile | null, fallback: string) => {
  const source = profile?.full_name || profile?.email || fallback;
  return source
    .split(/\s|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
};

const readOnlyFieldClass =
  "cursor-default hover:border-border focus:border-border";

type AvatarModalState = "closed" | "options";

export default function ProfileSettingPage() {
  const { t } = useTranslation("settings");
  const {
    profile,
    avatarHistory,
    formValues,
    editingProfile,
    loading,
    saving,
    avatarSaving,
    avatarHistoryLoading,
    profileChanged,
    passwordModalStep,
    newPassword,
    confirmPassword,
    passwordActionLoading,
    passwordSendConfirmOpen,
    deleteModalOpen,
    deleteLoading,
    setEditingProfile,
    setOtpCode,
    setNewPassword,
    setConfirmPassword,
    setPasswordModalStep,
    setPasswordSendConfirmOpen,
    setDeleteModalOpen,
    updateProfileField,
    handleSave,
    handleCancelEdit,
    handleUpdateAvatar,
    handleRemoveAvatar,
    handleSelectAvatar,
    openPasswordOTPModal,
    handleVerifyPasswordOTP,
    handleCompletePasswordChange,
    handleDeleteAccount,
  } = useProfileSettings();

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarModal, setAvatarModal] = useState<AvatarModalState>("closed");
  const [cropImage, setCropImage] = useState("");
  const [selectingAvatarId, setSelectingAvatarId] = useState<string | null>(
    null,
  );
  const initials = useMemo(
    () => getInitials(profile, t("profilePage.userFallback")),
    [profile, t],
  );
  const avatarPreview = profile?.avatar || "";

  useEffect(() => {
    return () => {
      if (cropImage) URL.revokeObjectURL(cropImage);
    };
  }, [cropImage]);

  const openAvatarModal = () => {
    setAvatarModal("options");
  };

  const openAvatarPicker = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarSelection = (file?: File) => {
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast.warning(t("profilePage.selectImage"));
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast.warning(t("imageSize"));
      return;
    }

    if (cropImage) URL.revokeObjectURL(cropImage);
    setAvatarModal("closed");
    setCropImage(URL.createObjectURL(file));
  };

  const closeCropModal = () => {
    if (cropImage) URL.revokeObjectURL(cropImage);
    setCropImage("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const confirmAvatarCrop = async (file: File) => {
    await handleUpdateAvatar(file);
    closeCropModal();
  };

  const removeAvatar = async () => {
    await handleRemoveAvatar();
    setAvatarModal("closed");
  };

  const selectAvatar = async (avatarId: string) => {
    setSelectingAvatarId(avatarId);
    try {
      await handleSelectAvatar(avatarId);
      setAvatarModal("closed");
    } finally {
      setSelectingAvatarId(null);
    }
  };

  return (
    <div className="w-full space-y-6">
      <section className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="flex flex-col">
          <div className="flex-1 rounded-surface border border-border bg-surface">
            <div className="flex flex-col items-center text-center p-6">
              <button
                type="button"
                onClick={openAvatarModal}
                disabled={loading || avatarSaving}
                className="group relative flex h-36 w-36 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary text-style-display font-bold text-color-primary-foreground outline-none ring-offset-2 transition focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-70"
                aria-label={t("profilePage.updateAvatar")}
                title={t("profilePage.updateAvatar")}
              >
                {avatarPreview ? (
                  <img
                    src={avatarPreview}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  initials
                )}
                <span className="absolute inset-0 flex items-center justify-center bg-overlay opacity-0 transition group-hover:opacity-100 group-focus:opacity-100">
                  <Camera className="h-7 w-7 text-color-foreground-inverse" />
                </span>
              </button>
              <h2 className="mt-5 max-w-full truncate text-style-section-title font-bold text-color-foreground">
                {profile?.full_name || t("profilePage.roleFallback")}
              </h2>
              <p className="mt-1 max-w-full truncate text-style-body text-color-muted-foreground">
                {profile?.email || t("profilePage.loading")}
              </p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) =>
                handleAvatarSelection(event.target.files?.[0])
              }
            />

            <div className="mx-auto h-px w-64 rounded-full bg-border" />

            <div className="p-6">
              <div className="space-y-3">
                <ReadOnlyRow
                  icon={<Mail className="h-4 w-4" />}
                  label={t("profilePage.email")}
                  value={profile?.email || t("statuses.unknown", { ns: "common" })}
                />
                <ReadOnlyRow
                  icon={<Fingerprint className="h-4 w-4" />}
                  label={t("profilePage.tenantId")}
                  value={profile?.tenant_id || t("statuses.unknown", { ns: "common" })}
                />
                <ReadOnlyRow
                  icon={<ShieldCheck className="h-4 w-4" />}
                  label={t("profilePage.provider")}
                  value={profile?.auth_provider || t("statuses.unknown", { ns: "common" })}
                />
                <ReadOnlyRow
                  icon={<CalendarDays className="h-4 w-4" />}
                  label={t("profilePage.joined")}
                  value={formatDate(
                    profile?.date_joined,
                    t("statuses.unknown", { ns: "common" }),
                  )}
                />
              </div>
            </div>
          </div>
        </aside>

        <div className="rounded-surface border border-border bg-surface p-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-style-heading text-color-foreground">
                {t("profileInformation")}
              </h3>
              {editingProfile ? (
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="md"
                    onClick={handleCancelEdit}
                  >
                    {t("apiKey.cancel")}
                  </Button>
                  <Button
                    id="btn-save-profile"
                    size="md"
                    loading={saving}
                    disabled={loading || !profileChanged}
                    onClick={handleSave}
                  >
                    {t("apiKey.save")}
                  </Button>
                </div>
              ) : (
                <Button
                  id="btn-edit-profile"
                  variant="secondary"
                  size="md"
                  onClick={() => setEditingProfile(true)}
                  disabled={loading}
                >
                  <Edit3 className="h-4 w-4" />
                  {t("editProfile")}
                </Button>
              )}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <Input
                id="profile-full-name"
                label={t("fullName")}
                icon={<UserRound className="h-4 w-4 text-color-muted-foreground" />}
                placeholder={t("profilePage.fullNamePlaceholder")}
                value={formValues.fullName}
                disabled={loading}
                readOnly={!editingProfile}
                tabIndex={!editingProfile ? -1 : undefined}
                className={!editingProfile ? readOnlyFieldClass : ""}
                onChange={(event) =>
                  updateProfileField("fullName", event.target.value)
                }
              />
              {editingProfile ? (
                <label
                  htmlFor="profile-pronouns"
                  className="flex flex-col gap-2 text-style-body-strong text-color-foreground"
                >
                  {t("pronouns")}
                  <div className="relative">
                    <Tags className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-color-muted-foreground" />
                    <select
                      id="profile-pronouns"
                      value={formValues.pronouns}
                      disabled={loading}
                      onChange={(event) =>
                        updateProfileField("pronouns", event.target.value)
                      }
                      className="h-14 w-full appearance-none rounded-control border border-border bg-surface pl-10 pr-10 text-style-body font-normal text-color-foreground outline-none transition-colors duration-200 hover:border-primary focus:border-primary disabled:bg-muted disabled:text-color-muted-foreground"
                    >
                      <option value="">{t("profilePage.pronounUnspecified")}</option>
                      <option value="he/him">{t("profilePage.pronounHe")}</option>
                      <option value="she/her">{t("profilePage.pronounShe")}</option>
                      <option value="they/them">{t("profilePage.pronounThey")}</option>
                      <option value="other">{t("profilePage.pronounOther")}</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-color-muted-foreground" />
                  </div>
                </label>
              ) : (
                <Input
                  id="profile-pronouns"
                  label={t("pronouns")}
                  icon={<Tags className="h-4 w-4 text-color-muted-foreground" />}
                  value={formValues.pronouns || t("profilePage.pronounUnspecified")}
                  disabled={loading}
                  readOnly
                  tabIndex={-1}
                  className={readOnlyFieldClass}
                />
              )}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <Input
                id="profile-company"
                label={t("company")}
                icon={<Building2 className="h-4 w-4 text-color-muted-foreground" />}
                placeholder={t("profilePage.companyPlaceholder")}
                value={formValues.company}
                disabled={loading}
                readOnly={!editingProfile}
                tabIndex={!editingProfile ? -1 : undefined}
                className={!editingProfile ? readOnlyFieldClass : ""}
                onChange={(event) =>
                  updateProfileField("company", event.target.value)
                }
              />
              <Input
                id="profile-field-of-work"
                label={t("fieldOfWork")}
                icon={
                  <BriefcaseBusiness className="h-4 w-4 text-color-muted-foreground" />
                }
                placeholder={t("profilePage.fieldPlaceholder")}
                value={formValues.fieldOfWork}
                disabled={loading}
                readOnly={!editingProfile}
                tabIndex={!editingProfile ? -1 : undefined}
                className={!editingProfile ? readOnlyFieldClass : ""}
                onChange={(event) =>
                  updateProfileField("fieldOfWork", event.target.value)
                }
              />
            </div>

            <Input
              id="profile-country"
              label={t("country")}
              icon={<Globe2 className="h-4 w-4 text-color-muted-foreground" />}
              placeholder={t("profilePage.countryPlaceholder")}
              value={formValues.country}
              disabled={loading}
              readOnly={!editingProfile}
              tabIndex={!editingProfile ? -1 : undefined}
              className={!editingProfile ? readOnlyFieldClass : ""}
              onChange={(event) =>
                updateProfileField("country", event.target.value)
              }
              onKeyDown={(event) => event.key === "Enter" && handleSave()}
            />

            <label
              htmlFor="profile-description"
              className="flex flex-col gap-2 text-style-body-strong text-color-foreground"
            >
              {t("description")}
              <div className="relative">
                <FileText className="pointer-events-none absolute left-3 top-4 h-4 w-4 text-color-muted-foreground" />
                <textarea
                  id="profile-description"
                  className={`text-style-body text-color-foreground placeholder:text-color-muted-foreground font-normal placeholder:font-normal min-h-24 w-full resize-y rounded-control border border-border bg-surface py-3 pl-10 pr-4 outline-none transition-colors duration-200 disabled:bg-muted disabled:text-color-muted-foreground ${
                    editingProfile
                      ? "hover:border-primary focus:border-primary"
                      : "cursor-default hover:border-border focus:border-border"
                  }`}
                  placeholder={t("profilePage.descriptionPlaceholder")}
                  value={formValues.description}
                  disabled={loading}
                  readOnly={!editingProfile}
                  tabIndex={!editingProfile ? -1 : undefined}
                  onChange={(event) =>
                    updateProfileField("description", event.target.value)
                  }
                />
              </div>
            </label>

            <div className="flex justify-end space-x-3 pt-1">
              <Button
                id="btn-change-password"
                variant="secondary"
                icon={<LockKeyhole className="h-4 w-4" />}
                onClick={() => setPasswordSendConfirmOpen(true)}
                disabled={loading}
              >
                {t("changePassword")}
              </Button>
              <Button
                id="btn-delete-account"
                variant="danger"
                icon={<Trash2 className="h-4 w-4" />}
                onClick={() => setDeleteModalOpen(true)}
                disabled={loading}
              >
                {t("deleteAccount")}
              </Button>
            </div>
          </div>
        </div>
      </section>

      <ConfirmModal
        open={passwordSendConfirmOpen}
        title={t("profilePage.passwordConfirmTitle")}
        description={t("profilePage.passwordConfirmDescription", {
          email: profile?.email,
        })}
        confirmText={t("profilePage.passwordConfirmAction")}
        loading={passwordActionLoading}
        onCancel={() => setPasswordSendConfirmOpen(false)}
        onConfirm={openPasswordOTPModal}
      />

      {passwordModalStep === "otp" && (
        <BaseModal
          title={t("profilePage.verifyOtpTitle")}
          onClose={() => setPasswordModalStep("closed")}
        >
          <p className="mb-4 text-style-body text-color-muted-foreground">
            {t("profilePage.otpDescription", { email: profile?.email })}
          </p>
          <OTPInput
            onComplete={(otp) => {
              setOtpCode(otp);
            }}
            disabled={passwordActionLoading}
          />
          <div className="mt-6 flex justify-end gap-3">
            <Button
              variant="secondary"
              onClick={() => setPasswordModalStep("closed")}
            >
              {t("actions.cancel", { ns: "common" })}
            </Button>
            <Button
              loading={passwordActionLoading}
              onClick={handleVerifyPasswordOTP}
            >
              {t("profilePage.verifyOtpAction")}
            </Button>
          </div>
        </BaseModal>
      )}

      {passwordModalStep === "password" && (
        <BaseModal
          title={t("profilePage.setPasswordTitle")}
          onClose={() => setPasswordModalStep("closed")}
        >
          <div className="space-y-4">
            <InputPassword
              id="input-change-new-password"
              label={t("profilePage.newPassword")}
              placeholder={t("profilePage.newPasswordPlaceholder")}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            <InputPassword
              id="input-change-confirm-password"
              label={t("profilePage.confirmPassword")}
              placeholder={t("profilePage.confirmPasswordPlaceholder")}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              onKeyDown={(event) =>
                event.key === "Enter" && handleCompletePasswordChange()
              }
            />
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <Button
              variant="secondary"
              onClick={() => setPasswordModalStep("closed")}
            >
              {t("apiKey.cancel")}
            </Button>
            <Button
              loading={passwordActionLoading}
              onClick={handleCompletePasswordChange}
            >
              {t("changePassword")}
            </Button>
          </div>
        </BaseModal>
      )}

      <ConfirmModal
        open={deleteModalOpen}
        title={t("deleteTitle")}
        tone="danger"
        description={
          <div className="space-y-3">
            <p>{t("profilePage.deleteDescription")}</p>
            <p className="font-semibold text-color-foreground">
              {t("profilePage.deleteConfirmation", {
                email: profile?.email || t("profilePage.userFallback"),
              })}
            </p>
          </div>
        }
        confirmText={t("deleteAccount")}
        loading={deleteLoading}
        onCancel={() => setDeleteModalOpen(false)}
        onConfirm={handleDeleteAccount}
      />

      <AvatarModal
        open={avatarModal === "options"}
        avatarPreview={avatarPreview}
        avatarHistory={avatarHistory}
        historyLoading={avatarHistoryLoading}
        selectingAvatarId={selectingAvatarId}
        onClose={() => setAvatarModal("closed")}
        onRemove={removeAvatar}
        onChange={openAvatarPicker}
        onSelectAvatar={selectAvatar}
      />

      <AvatarCropModal
        imageSrc={cropImage}
        loading={avatarSaving}
        onClose={closeCropModal}
        onConfirm={confirmAvatarCrop}
        onError={() =>
          toast.error(t("profilePage.cropFailed"))
        }
      />
    </div>
  );
}

function ReadOnlyRow({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-compact bg-muted px-3 py-3">
      <span className="mt-0.5 text-color-muted-foreground">{icon}</span>
      <div className="min-w-0">
        <p className="text-style-overline uppercase text-color-muted-foreground">
          {label}
        </p>
        <p className="truncate text-style-body-strong text-color-foreground">
          {value}
        </p>
      </div>
    </div>
  );
}

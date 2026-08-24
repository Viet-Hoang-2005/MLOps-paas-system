import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  completePasswordChange,
  deleteAccount,
  getProfile,
  listProfileAvatars,
  requestPasswordChangeOTP,
  selectProfileAvatar,
  updateProfile,
  updateProfileAvatar,
  verifyPasswordChangeOTP,
} from '@/features/settings/api/profileApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { settingsQueryKeys } from '@/features/settings/queryKeys';
import { toast } from '@/shared/components/toastStore';
import type { PasswordModalStep, ProfileFormValues, UpdateProfileRequest, UserProfile } from '@/features/settings/types';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useTranslation } from 'react-i18next';

export const emptyProfileForm: ProfileFormValues = {
  fullName: '',
  description: '',
  pronouns: '',
  company: '',
  fieldOfWork: '',
  country: '',
};

const profileToForm = (profile: UserProfile): ProfileFormValues => ({
  fullName: profile.full_name || '',
  description: profile.description || '',
  pronouns: profile.pronouns || '',
  company: profile.company || '',
  fieldOfWork: profile.field_of_work || '',
  country: profile.country || '',
});

export function useProfileSettings() {
  const { logout } = useAuth();
  const { t } = useTranslation('settings');
  const queryClient = useQueryClient();
  const [draftFormValues, setDraftFormValues] = useState<ProfileFormValues>(emptyProfileForm);
  const [editingProfile, setEditingProfile] = useState(false);
  const [passwordModalStep, setPasswordModalStep] = useState<PasswordModalStep>('closed');
  const [otpCode, setOtpCode] = useState('');
  const [passwordChangeToken, setPasswordChangeToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordActionLoading, setPasswordActionLoading] = useState(false);
  const [passwordSendConfirmOpen, setPasswordSendConfirmOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const profileQuery = useQuery({
    queryKey: settingsQueryKeys.profile(),
    queryFn: getProfile,
  });
  const avatarHistoryQuery = useQuery({
    queryKey: settingsQueryKeys.avatars(),
    queryFn: listProfileAvatars,
  });

  const profile = profileQuery.data ?? null;
  const profileFormValues = useMemo(
    () => (profile ? profileToForm(profile) : emptyProfileForm),
    [profile],
  );
  const formValues = editingProfile ? draftFormValues : profileFormValues;

  useEffect(() => {
    if (profileQuery.isError) {
      toast.error(getApiErrorMessage(profileQuery.error, t('profilePage.loadFailed')));
    }
  }, [profileQuery.error, profileQuery.isError, t]);

  const updateProfileMutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: (_response, variables: UpdateProfileRequest) => {
      const updatedProfile = profile
        ? {
            ...profile,
            full_name: variables.full_name,
            description: variables.description,
            pronouns: variables.pronouns,
            company: variables.company,
            field_of_work: variables.field_of_work,
            country: variables.country,
          }
        : null;

      if (updatedProfile) {
        queryClient.setQueryData<UserProfile>(settingsQueryKeys.profile(), updatedProfile);
      }
      setEditingProfile(false);
      toast.success(t('profilePage.updateSuccess'));
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('profilePage.updateFailed')));
    },
  });

  const updateAvatarMutation = useMutation({
    mutationFn: updateProfileAvatar,
    onSuccess: async (_response, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: settingsQueryKeys.profile() }),
        queryClient.invalidateQueries({ queryKey: settingsQueryKeys.avatars() }),
      ]);
      toast.success(variables.remove_avatar ? t('profilePage.avatarRemoved') : t('profilePage.avatarUpdated'));
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('profilePage.avatarUpdateFailed')));
    },
  });

  const selectAvatarMutation = useMutation({
    mutationFn: selectProfileAvatar,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: settingsQueryKeys.profile() }),
        queryClient.invalidateQueries({ queryKey: settingsQueryKeys.avatars() }),
      ]);
      toast.success(t('profilePage.avatarSelected'));
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t('profilePage.avatarSelectFailed')));
    },
  });

  const profileChanged = useMemo(
    () => editingProfile && JSON.stringify(draftFormValues) !== JSON.stringify(profileFormValues),
    [draftFormValues, editingProfile, profileFormValues],
  );

  const updateProfileField = (field: keyof ProfileFormValues, value: string) => {
    setDraftFormValues((current) => ({ ...current, [field]: value }));
  };

  const setProfileEditing = (editing: boolean) => {
    if (editing) {
      setDraftFormValues(profileFormValues);
    }
    setEditingProfile(editing);
  };

  const handleSave = async () => {
    updateProfileMutation.mutate({
      full_name: formValues.fullName,
      description: formValues.description,
      pronouns: formValues.pronouns,
      company: formValues.company,
      field_of_work: formValues.fieldOfWork,
      country: formValues.country,
    });
  };

  const handleCancelEdit = () => {
    setDraftFormValues(profileFormValues);
    setEditingProfile(false);
  };

  const handleUpdateAvatar = async (avatar: File) => {
    await updateAvatarMutation.mutateAsync({ avatar });
  };

  const handleRemoveAvatar = async () => {
    await updateAvatarMutation.mutateAsync({ remove_avatar: true });
  };

  const handleSelectAvatar = async (avatarId: string) => {
    await selectAvatarMutation.mutateAsync(avatarId);
  };

  const openPasswordOTPModal = async () => {
    setPasswordSendConfirmOpen(false);
    setPasswordModalStep('otp');
    setOtpCode('');
    setPasswordChangeToken('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordActionLoading(true);
    try {
      await requestPasswordChangeOTP();
      toast.success(t('profilePage.otpSent'));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('profilePage.otpSendFailed')));
    } finally {
      setPasswordActionLoading(false);
    }
  };

  const handleVerifyPasswordOTP = async () => {
    if (otpCode.trim().length !== 6) {
      toast.warning(t('profilePage.otpInvalidFormat'));
      return;
    }

    setPasswordActionLoading(true);
    try {
      const response = await verifyPasswordChangeOTP(otpCode.trim());
      setPasswordChangeToken(response.password_change_token);
      setPasswordModalStep('password');
      toast.success(t('profilePage.otpVerified'));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('profilePage.otpInvalid')));
    } finally {
      setPasswordActionLoading(false);
    }
  };

  const handleCompletePasswordChange = async () => {
    if (newPassword.length < 8) {
      toast.warning(t('profilePage.passwordTooShort'));
      return;
    }

    if (newPassword !== confirmPassword) {
      toast.warning(t('profilePage.passwordMismatch'));
      return;
    }

    setPasswordActionLoading(true);
    try {
      await completePasswordChange(passwordChangeToken, newPassword);
      toast.success(t('profilePage.passwordChanged'));
      setPasswordModalStep('closed');
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('profilePage.passwordChangeFailed')));
    } finally {
      setPasswordActionLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteLoading(true);
    try {
      await deleteAccount();
      toast.success(t('profilePage.accountDeleted'));
      queryClient.clear();
      logout();
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('profilePage.accountDeleteFailed')));
    } finally {
      setDeleteLoading(false);
    }
  };

  return {
    profile,
    avatarHistory: avatarHistoryQuery.data?.avatars ?? [],
    formValues,
    editingProfile,
    loading: profileQuery.isLoading,
    saving: updateProfileMutation.isPending,
    avatarSaving: updateAvatarMutation.isPending,
    avatarHistoryLoading: avatarHistoryQuery.isLoading,
    selectingAvatar: selectAvatarMutation.isPending,
    profileChanged,
    passwordModalStep,
    otpCode,
    newPassword,
    confirmPassword,
    passwordActionLoading,
    passwordSendConfirmOpen,
    deleteModalOpen,
    deleteLoading,
    setEditingProfile: setProfileEditing,
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
  };
}

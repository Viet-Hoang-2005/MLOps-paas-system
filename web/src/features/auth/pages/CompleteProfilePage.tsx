import { Link, Navigate, useLocation } from 'react-router-dom';
import { ArrowLeft, Camera, User, Lock, LockKeyhole } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { AuthCard } from '@/features/auth/components/AuthCard';
import { Input, InputPassword } from '@/shared/components/Input';
import { Button } from '@/shared/components/Button';
import { AvatarCropModal } from '@/features/settings/components/AvatarCropModal';
import { AvatarModal } from '@/features/settings/components/AvatarModal';
import { toast } from '@/shared/components/toastStore';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useForm } from '@/features/auth/hooks/useForm';
import { completeRegistration } from '@/features/auth/api/authApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { useTranslation } from 'react-i18next';

interface LocationState {
  registrationToken: string;
  email: string;
}

type AvatarModalState = 'closed' | 'options';

export default function CompleteProfilePage() {
  const { t } = useTranslation('auth');
  const location = useLocation();
  const { registrationToken, email } = (location.state as LocationState) || {
    registrationToken: '',
    email: '',
  };

  const { saveAuthTokens } = useAuth();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState('');
  const [cropImage, setCropImage] = useState('');
  const [avatarModal, setAvatarModal] = useState<AvatarModalState>('closed');

  const { values, errors, loading, updateField, handleSubmit } = useForm(
    { full_name: '', password: '', confirmPassword: '' },
    {
      full_name: (value: string) => !value ? t('profile.fullNameRequired') : undefined,
      password: (value: string) => !value ? t('profile.passwordRequired') : value.length < 8 ? t('profile.passwordLength') : undefined,
      confirmPassword: (value: string, all: Record<string, string>) => value !== all.password ? t('profile.mismatch') : undefined,
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

    if (!file.type.startsWith('image/')) {
      toast.warning(t('profile.imageOnly'));
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast.warning(t('profile.imageSize'));
      return;
    }

    if (cropImage) URL.revokeObjectURL(cropImage);
    const nextCropImage = URL.createObjectURL(file);
    setAvatarModal('closed');
    setCropImage(nextCropImage);
  };

  const closeCropModal = () => {
    if (cropImage) URL.revokeObjectURL(cropImage);
    setCropImage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const confirmAvatarCrop = (croppedFile: File) => {
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    setAvatarFile(croppedFile);
    setAvatarPreview(URL.createObjectURL(croppedFile));
    closeCropModal();
  };

  const openAvatarModal = () => {
    setAvatarModal('options');
  };

  const openAvatarPicker = () => {
    fileInputRef.current?.click();
  };

  const removeAvatar = () => {
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
    setAvatarFile(null);
    setAvatarPreview('');
    setAvatarModal('closed');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
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
      toast.success(t('profile.success'));
      saveAuthTokens(response.access, response.refresh, '/dashboard', response.tenant_id);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('profile.failed')));
    }
  });

  if (!registrationToken) {
    return <Navigate to="/signup" replace />;
  }

  return (
    <AuthCard>
      <div className="max-w-sm w-full mx-auto">
        <Link
          to="/signup"
          className="mb-4 flex items-center gap-2 text-style-body text-color-muted-foreground hover:text-color-foreground
                    font-medium transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="">{t('profile.back')}</span>
        </Link>

        <h2 className="mb-1 text-style-page-title font-bold text-color-foreground">{t('profile.title')}</h2>
        <p className="mb-6 text-style-body text-color-muted-foreground">
          {t('profile.registering', { email })}
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
            aria-label={t('profile.setAvatar')}
            title={t('profile.setAvatar')}
            className="flex w-full items-center justify-between gap-4 rounded-control border border-border bg-surface px-4 py-3 text-left transition-colors hover:border-primary focus:border-primary focus:outline-none"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-color-muted-foreground">
                {avatarPreview ? (
                  <img src={avatarPreview} alt={t('profile.avatarPreview')} className="h-full w-full object-cover" />
                ) : (
                  <Camera className="h-5 w-5" />
                )}
              </div>
              <div>
                <p className="text-style-body-strong text-color-foreground">{t('profile.avatar')}</p>
                <p className="text-style-caption text-color-muted-foreground">{t('profile.avatarDescription')}</p>
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
            label={t('profile.fullName')}
            placeholder={t('profile.fullNamePlaceholder')}
            icon={<User className="h-4 w-4" />}
            value={values.full_name}
            error={errors.full_name}
            onChange={(e) => updateField('full_name', e.target.value)}
          />
          <InputPassword
            id="input-new-password"
            name="new-password"
            autoComplete="new-password"
            label={t('profile.password')}
            placeholder={t('profile.passwordPlaceholder')}
            icon={<Lock className="h-4 w-4" />}
            value={values.password}
            error={errors.password}
            onChange={(e) => updateField('password', e.target.value)}
          />
          <InputPassword
            id="input-confirm-password"
            name="confirm-password"
            autoComplete="new-password"
            label={t('profile.confirm')}
            placeholder={t('profile.confirmPlaceholder')}
            icon={<LockKeyhole className="h-4 w-4" />}
            value={values.confirmPassword}
            error={errors.confirmPassword}
            onChange={(e) => updateField('confirmPassword', e.target.value)}
          />

          <Button
            id="btn-create-account"
            type="submit"
            variant="primary"
            fullWidth
            loading={loading}
            className="mt-6"
          >
            {t('profile.submit')}
          </Button>
        </form>
      </div>

      <AvatarModal
        open={avatarModal === 'options'}
        avatarPreview={avatarPreview}
        onClose={() => setAvatarModal('closed')}
        onRemove={removeAvatar}
        onChange={openAvatarPicker}
      />

      <AvatarCropModal
        imageSrc={cropImage}
        onClose={closeCropModal}
        onConfirm={confirmAvatarCrop}
        onError={() => toast.error(t('profile.cropFailed'))}
      />
    </AuthCard>
  );
}

import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, LockKeyhole } from 'lucide-react';
import { AuthCard } from '@/features/auth/components/AuthCard';
import { Button } from '@/shared/components/Button';
import { InputPassword } from '@/shared/components/Input';
import { useForm } from '@/features/auth/hooks/useForm';
import { resetForgottenPassword } from '@/features/auth/api/authApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { toast } from '@/shared/components/toastStore';
import { useTranslation } from 'react-i18next';

interface LocationState {
  email: string;
  resetToken: string;
}

export default function ForgotPasswordResetPage() {
  const { t } = useTranslation('auth');
  const navigate = useNavigate();
  const location = useLocation();
  const { email, resetToken } = (location.state as LocationState) || {
    email: '',
    resetToken: '',
  };

  const { values, errors, loading, updateField, handleSubmit } = useForm(
    { password: '', confirmPassword: '' },
    {
      password: (value: string) => !value ? t('profile.passwordRequired') : value.length < 8 ? t('profile.passwordLength') : undefined,
      confirmPassword: (value: string, all: Record<string, string>) => value !== all.password ? t('profile.mismatch') : undefined,
    },
  );

  const onSubmit = handleSubmit(async (formValues) => {
    try {
      await resetForgottenPassword(resetToken, formValues.password);
      toast.success(t('recovery.resetSuccess'));
      navigate('/login', { replace: true });
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('recovery.resetFailed')));
    }
  });

  if (!resetToken) {
    return <Navigate to="/forgot-password" replace />;
  }

  return (
    <AuthCard>
      <div className="max-w-sm w-full mx-auto">
        <Link
          to="/forgot-password"
          className="mb-8 flex items-center gap-2 text-style-body text-color-muted-foreground hover:text-color-foreground
                    font-medium transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="">{t('recovery.startOver')}</span>
        </Link>

        <div className="mb-4 rounded-surface flex items-center justify-center mx-auto">
          <LockKeyhole className="h-8 w-8 text-color-foreground" />
        </div>

        <h2 className="mb-2 text-center text-style-page-title font-bold text-color-foreground">{t('recovery.newTitle')}</h2>
        <p className="mb-8 text-center text-style-body text-color-muted-foreground">
          {t('recovery.newDescription', { email })}
        </p>

        <div className="flex flex-col gap-4">
          <InputPassword
            id="input-reset-password"
            name="new-password"
            autoComplete="new-password"
            label={t('recovery.newPassword')}
            placeholder={t('recovery.passwordPlaceholder')}
            value={values.password}
            error={errors.password}
            onChange={(event) => updateField('password', event.target.value)}
          />
          <InputPassword
            id="input-confirm-reset-password"
            name="confirm-password"
            autoComplete="new-password"
            label={t('recovery.confirmPassword')}
            placeholder={t('recovery.confirmPlaceholder')}
            value={values.confirmPassword}
            error={errors.confirmPassword}
            onChange={(event) => updateField('confirmPassword', event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && onSubmit()}
          />
          <Button
            id="btn-reset-password"
            variant="primary"
            fullWidth
            loading={loading}
            onClick={onSubmit}
            className="mt-4"
          >
            {t('recovery.reset')}
          </Button>
        </div>
      </div>
    </AuthCard>
  );
}

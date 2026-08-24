import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, ArrowLeft } from 'lucide-react';
import { AuthCard } from '@/features/auth/components/AuthCard';
import { Input } from '@/shared/components/Input';
import { Button } from '@/shared/components/Button';
import { toast } from '@/shared/components/toastStore';
import { forgotPasswordOTP } from '@/features/auth/api/authApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { useTranslation } from 'react-i18next';

export default function ForgotPasswordPage() {
  const { t } = useTranslation('auth');
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSendOTP = async () => {
    if (!email) {
      toast.warning(t('signup.emailRequired'));
      return;
    }
    setLoading(true);
    try {
      const response = await forgotPasswordOTP(email);
      toast.success(t('signup.otpSent'));
      navigate('/forgot-password/verify-otp', {
        state: { email: response.email || email.trim().toLowerCase() },
      });
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('recovery.sendFailed')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard>
      <div className="max-w-sm w-full mx-auto">
        {/* Back to Login */}
        <Link
          to="/login"
          className="mb-8 flex items-center gap-2 text-style-body text-color-muted-foreground hover:text-color-foreground
                    font-medium transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="">{t('recovery.backToSignIn')}</span>
        </Link>

        {/* Icon */}
        <div className="mb-4 rounded-surface flex items-center justify-center mx-auto">
          <Mail className="h-8 w-8 text-color-foreground" />
        </div>

        <h2 className="mb-2 text-center text-style-page-title font-bold text-color-foreground">{t('recovery.title')}</h2>
        <p className="mb-6 text-center text-style-body text-color-muted-foreground">
          {t('recovery.description')}
        </p>

        <div className="flex flex-col gap-4">
          <Input
            id="input-forgot-email"
            name="email"
            autoComplete="email"
            label={t('login.email')}
            type="email"
            placeholder={t('login.emailPlaceholder')}
            icon={<Mail className="h-4 w-4" />}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendOTP()}
          />
          <Button
            id="btn-send-otp"
            variant="primary"
            fullWidth
            loading={loading}
            onClick={handleSendOTP}
            className="mt-4"
          >
            {t('recovery.send')}
          </Button>
        </div>
      </div>
    </AuthCard>
  );
}

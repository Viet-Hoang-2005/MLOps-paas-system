import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Mail, ArrowLeft } from 'lucide-react';
import { AuthCard } from '@/features/auth/components/AuthCard';
import { OTPInput } from '@/shared/components/OTPInput';
import { Button } from '@/shared/components/Button';
import { toast } from '@/shared/components/toastStore';
import { useCountdown } from '@/features/auth/hooks/useCountdown';
import { verifyOTP, requestOTP } from '@/features/auth/api/authApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface LocationState {
  email: string;
}

export default function SignUpOTPPage() {
  const { t } = useTranslation('auth');
  const navigate = useNavigate();
  const location = useLocation();
  const { email } = (location.state as LocationState) || { email: '' };

  const { seconds, isRunning, reset: resetCountdown } = useCountdown(60);

  const [loading, setLoading] = useState(false);
  const [otpValue, setOtpValue] = useState('');

  const handleVerify = async (otp?: string) => {
    const code = otp || otpValue;
    if (code.length !== 6) {
      toast.warning(t('otp.invalid'));
      return;
    }
    setLoading(true);
    try {
      const response = await verifyOTP({ email, otp_code: code });
      toast.success(t('otp.verified'));
      navigate('/signup/complete-profile', {
        state: { registrationToken: response.registration_token, email },
      });
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('otp.expired')));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    try {
      await requestOTP({ email });
      toast.success(t('otp.resent'));
      resetCountdown();
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('otp.resendFailed')));
    }
  };

  const handleOTPComplete = (otp: string) => {
    setOtpValue(otp);
    handleVerify(otp);
  };

  if (!email) {
    navigate('/signup');
    return null;
  }

  return (
    <AuthCard>
      <div className="flex flex-col max-w-sm w-full mx-auto text-center gap-8">
        <Link
          to="/signup"
          className="flex items-center gap-2 text-style-body text-color-muted-foreground hover:text-color-foreground
                    font-medium transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="">{t('otp.back')}</span>
        </Link>

        <div className="flex flex-col items-center justify-center gap-3">
          <Mail className="h-8 w-8 text-color-foreground" />
          <h2 className="text-style-page-title font-bold text-color-foreground">{t('otp.title')}</h2>
          <p className="text-style-body text-color-muted-foreground">
            {t('otp.description', { email })}
          </p>
        </div>

        <OTPInput onComplete={handleOTPComplete} disabled={loading} />

        <Button
          id="btn-verify-otp"
          variant="primary"
          fullWidth
          loading={loading}
          onClick={() => handleVerify()}
        >
          {t('otp.verify')}
        </Button>

        <p className="text-style-body text-color-muted-foreground">
          {t('otp.missing')}{' '}
          {isRunning ? (
            <span className="font-semibold text-color-muted-foreground">
              {t('otp.resendIn', { seconds })}
            </span>
          ) : (
            <button
              onClick={handleResend}
              className="cursor-pointer font-semibold text-color-foreground hover:text-color-primary-hover"
            >
              {t('otp.resend')}
            </button>
          )}
        </p>
      </div>
    </AuthCard>
  );
}

import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useCountdown – Đếm ngược từ một số giây và tự dừng khi về 0.
 * Hữu ích cho tính năng "Resend OTP after Xs".
 *
 * @param initialSeconds – Số giây đếm ngược (mặc định: 60)
 * @param autoStart – Tự động bắt đầu đếm ngay khi hook được khởi tạo (mặc định: true)
 *
 * @example
 * const { seconds, isRunning, start, reset } = useCountdown(60);
 *
 * // Trong JSX:
 * <button disabled={isRunning} onClick={() => { resend(); reset(); }}>
 *   {isRunning ? `Resend in ${seconds}s` : 'Resend code'}
 * </button>
 */
export function useCountdown(initialSeconds = 60, autoStart = true) {
  const [seconds, setSeconds] = useState(autoStart ? initialSeconds : 0);
  const [isRunning, setIsRunning] = useState(autoStart);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsRunning(false);
  }, []);

  const start = useCallback(() => {
    stop(); // Dừng interval cũ nếu đang chạy
    setSeconds(initialSeconds);
    setIsRunning(true);
  }, [initialSeconds, stop]);

  const reset = useCallback(() => {
    start();
  }, [start]);

  useEffect(() => {
    if (!isRunning) return;

    intervalRef.current = setInterval(() => {
      setSeconds((prev) => {
        if (prev <= 1) {
          stop();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRunning, stop]);

  return { seconds, isRunning, start, stop, reset };
}

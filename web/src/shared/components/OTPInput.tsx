import { useRef, useState, useCallback } from "react";
import type { KeyboardEvent, ClipboardEvent, ChangeEvent } from "react";

interface OTPInputProps {
  length?: number;
  onComplete: (otp: string) => void;
  disabled?: boolean;
}

export function OTPInput({
  length = 6,
  onComplete,
  disabled = false,
}: OTPInputProps) {
  const [values, setValues] = useState<string[]>(Array(length).fill(""));
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const focusInput = useCallback(
    (index: number) => {
      if (index >= 0 && index < length) {
        inputRefs.current[index]?.focus();
      }
    },
    [length],
  );

  const handleChange = (index: number, e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    // Chỉ cho phép số
    if (val && !/^\d$/.test(val)) return;

    const newValues = [...values];
    newValues[index] = val;
    setValues(newValues);

    if (val && index < length - 1) {
      focusInput(index + 1);
    }

    // Tự động gọi onComplete khi nhập đủ
    const otpString = newValues.join("");
    if (otpString.length === length && !newValues.includes("")) {
      onComplete(otpString);
    }
  };

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      if (!values[index] && index > 0) {
        focusInput(index - 1);
        const newValues = [...values];
        newValues[index - 1] = "";
        setValues(newValues);
      }
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pastedData = e.clipboardData
      .getData("text")
      .replace(/\D/g, "")
      .slice(0, length);
    if (pastedData.length === 0) return;

    const newValues = [...values];
    for (let i = 0; i < pastedData.length; i++) {
      newValues[i] = pastedData[i];
    }
    setValues(newValues);
    focusInput(Math.min(pastedData.length, length - 1));

    if (pastedData.length === length) {
      onComplete(pastedData);
    }
  };

  return (
    <div className="flex gap-3 justify-center">
      {values.map((val, index) => (
        <input
          key={index}
          ref={(el) => {
            inputRefs.current[index] = el;
          }}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={val}
          disabled={disabled}
          onChange={(e) => handleChange(index, e)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={index === 0 ? handlePaste : undefined}
          className="w-12 h-14 text-center text-style-section-title font-bold border-2 border-border rounded-control
                     focus:border-primary focus:ring-2 focus:ring-primary/20 focus:outline-none
                     transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed
                     bg-surface text-color-foreground"
          autoFocus={index === 0}
        />
      ))}
    </div>
  );
}

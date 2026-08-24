import { useState, useCallback } from 'react';

type FieldValues = Record<string, string>;

type ValidationRules<T extends FieldValues> = Partial<
  Record<keyof T, (value: string, allValues: T) => string | undefined>
>;

/**
 * useForm – Quản lý giá trị, lỗi và trạng thái submit của form.
 * 
 * @param initialValues – Giá trị mặc định của form
 * @param validationRules – Object chứa các hàm validate cho từng field (tuỳ chọn)
 * 
 * @example
 * const { values, errors, loading, updateField, handleSubmit } = useForm(
 *   { email: '', password: '' },
 *   { email: (v) => !v ? 'Required' : undefined }
 * );
 */
export function useForm<T extends FieldValues>(
  initialValues: T,
  validationRules?: ValidationRules<T>,
) {
  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});
  const [loading, setLoading] = useState(false);

  /** Cập nhật một field */
  const updateField = useCallback((field: keyof T, value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }));
    // Xoá lỗi của field khi người dùng bắt đầu nhập lại
    if (errors[field]) {
      setErrors((prev) => ({ ...prev, [field]: undefined }));
    }
  }, [errors]);

  /** Chạy validate toàn bộ form, trả về true nếu hợp lệ */
  const validate = useCallback((): boolean => {
    if (!validationRules) return true;

    const newErrors: Partial<Record<keyof T, string>> = {};
    let isValid = true;

    for (const field in validationRules) {
      const rule = validationRules[field];
      if (rule) {
        const errorMsg = rule(values[field] ?? '', values);
        if (errorMsg) {
          newErrors[field] = errorMsg;
          isValid = false;
        }
      }
    }

    setErrors(newErrors);
    return isValid;
  }, [validationRules, values]);

  /**
   * Bọc hàm submit async: tự chạy validate, bật/tắt loading
   * @param submitFn – Hàm xử lý nghiệp vụ thực sự
   */
  const handleSubmit = useCallback(
    (submitFn: (values: T) => Promise<void>) =>
      async () => {
        if (!validate()) return;
        setLoading(true);
        try {
          await submitFn(values);
        } finally {
          setLoading(false);
        }
      },
    [validate, values],
  );

  /** Reset form về trạng thái ban đầu */
  const reset = useCallback(() => {
    setValues(initialValues);
    setErrors({});
  }, [initialValues]);

  return { values, errors, loading, updateField, handleSubmit, validate, reset };
}

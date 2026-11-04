import axios from "axios";

/** Only an authentication rejection proves that the refresh session is unusable. */
export const isInvalidRefreshSession = (error: unknown): boolean => {
  if (!axios.isAxiosError(error)) return false;
  if (error.response?.status === 401) return true;

  // The cookie refresh API has no authentication challenge, so DRF can return
  // authentication failures as 403. A CSRF/Origin 403 must remain recoverable.
  const code = error.response?.data?.error?.code;
  return (
    error.response?.status === 403 &&
    (code === "authentication_failed" || code === "token_not_valid")
  );
};

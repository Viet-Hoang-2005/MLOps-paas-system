const AUTH_CHANNEL_NAME = "mlops_paas_auth_channel";
const REFRESH_LOCK_NAME = "mlops_paas_token_refresh";

let broadcastChannelInstance: BroadcastChannel | null = null;

const getBroadcastChannel = (): BroadcastChannel | null => {
  if (typeof window === "undefined" || !("BroadcastChannel" in window)) {
    return null;
  }
  if (!broadcastChannelInstance) {
    broadcastChannelInstance = new BroadcastChannel(AUTH_CHANNEL_NAME);
  }
  return broadcastChannelInstance;
};

export async function runWithRefreshLock<T>(
  action: () => Promise<T>,
): Promise<T> {
  if (
    typeof navigator !== "undefined" &&
    "locks" in navigator &&
    typeof navigator.locks?.request === "function"
  ) {
    return navigator.locks.request(REFRESH_LOCK_NAME, () => action());
  }
  return action();
}

export const initAuthBroadcast = (onLogout: () => void): (() => void) => {
  const channel = getBroadcastChannel();
  if (!channel) return () => {};

  const handleMessage = (event: MessageEvent) => {
    if (event.data?.type === "AUTH_LOGGED_OUT") onLogout();
  };

  channel.addEventListener("message", handleMessage);
  return () => channel.removeEventListener("message", handleMessage);
};

export const broadcastLogout = (): void => {
  getBroadcastChannel()?.postMessage({ type: "AUTH_LOGGED_OUT" });
};

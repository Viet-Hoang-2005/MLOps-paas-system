import { useTranslation } from "react-i18next";
import { Callout } from "./Callout";

export function ExecutionObservation({
  state,
}: {
  state?: { observation_status?: "ok" | "retrying" | "cleanup_pending" } | null;
}) {
  const { t } = useTranslation("common");
  if (!state?.observation_status || state.observation_status === "ok")
    return null;
  return (
    <Callout
      variant="warning"
      description={t(`execution.${state.observation_status}`)}
      role="status"
    />
  );
}

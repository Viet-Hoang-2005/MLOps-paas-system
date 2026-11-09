import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createWorkspace } from "@/features/training/api/workspacesApi";
import { Button } from "@/shared/components/Button";
import { getApiErrorMessage } from "@/shared/api/errors";

export default function NewTrainingWorkspacePage() {
  const navigate = useNavigate(); const [params] = useSearchParams();
  const { t } = useTranslation("training");
  const started = useRef(false); const [error, setError] = useState("");
  async function create() {
    setError("");
    try { const workspace = await createWorkspace(); navigate(`/dashboard/training/workspaces/${workspace.id}${params.get("project") ? `?project=${encodeURIComponent(params.get("project")!)}` : ""}`, { replace: true }); }
    catch (failure) { setError(getApiErrorMessage(failure, t("studio.failed"))); }
  }
  useEffect(() => { if (!started.current) { started.current = true; void create(); } });
  return <div className="space-y-4 p-6 text-style-body"><p>{error || t("studio.creating")}</p>{error && <Button onClick={() => void create()}>{t("studio.reload")}</Button>}</div>;
}

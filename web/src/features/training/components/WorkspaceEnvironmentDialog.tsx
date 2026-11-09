import { useState } from "react";
import { useTranslation } from "react-i18next";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { deleteWorkspaceSecret, putWorkspaceSecret, updateWorkspace, type TrainingWorkspace } from "@/features/training/api/workspacesApi";

export function WorkspaceEnvironmentDialog({ workspace, onRefresh, onClose }: { workspace: TrainingWorkspace; onRefresh: () => Promise<TrainingWorkspace>; onClose: () => void }) {
  const { t } = useTranslation("training");
  const [name, setName] = useState(""); const [value, setValue] = useState("");
  const [secret, setSecret] = useState(false); const [busy, setBusy] = useState(false);
  async function execute(action: () => Promise<unknown>) {
    setBusy(true);
    try { await action(); setValue(""); setName(""); await onRefresh(); }
    catch (error) { toast.error(getApiErrorMessage(error, t("studio.failed"))); }
    finally { setBusy(false); }
  }
  return <BaseDialog title={t("studio.environment")} onClose={onClose} description={t("studio.secretWarning")}>
    <div className="space-y-4">
      <p className="text-style-caption text-color-muted-foreground">{t("studio.secretWarning")}</p>
      {!workspace.secrets_available && <p className="text-style-caption text-color-warning">{t("studio.secretsUnavailable")}</p>}
      {Object.entries(workspace.environment).map(([key, text]) => <div key={key} className="flex items-center gap-3 text-style-body">
        <span className="min-w-0 flex-1 break-all">{key} = {text}</span>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => { setName(key); setValue(text); setSecret(false); }}>{t("studio.edit")}</Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => void execute(async () => { const next = { ...workspace.environment }; delete next[key]; await updateWorkspace(workspace.id, workspace.revision, { environment: next }); })}>{t("studio.delete")}</Button>
      </div>)}
      {workspace.secrets.map((item) => <div key={item.name} className="flex items-center gap-3 text-style-body">
        <span className="min-w-0 flex-1 break-all">{item.name} · {t("studio.secretSaved")}</span>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => { setName(item.name); setValue(""); setSecret(true); }}>{t("studio.replaceValue")}</Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => void execute(() => deleteWorkspaceSecret(workspace.id, workspace.revision, item.name))}>{t("studio.delete")}</Button>
      </div>)}
      <form className="space-y-3 border-t border-border pt-4" onSubmit={(event) => { event.preventDefault(); void execute(() => secret ? putWorkspaceSecret(workspace.id, workspace.revision, name, value) : updateWorkspace(workspace.id, workspace.revision, { environment: { ...workspace.environment, [name]: value } })); }}>
        <Input label={t("studio.key")} value={name} required disabled={busy} onChange={(event) => setName(event.target.value)} />
        <Input label={t("studio.value")} type={secret ? "password" : "text"} value={value} required={secret} disabled={busy} autoComplete="off" onChange={(event) => setValue(event.target.value)} />
        <label className="flex items-center gap-2 text-style-body"><input type="checkbox" checked={secret} disabled={busy || !workspace.secrets_available} onChange={(event) => { setSecret(event.target.checked); setValue(""); }} />{t("studio.secret")}</label>
        <Button type="submit" loading={busy}>{t("studio.save")}</Button>
      </form>
    </div>
  </BaseDialog>;
}

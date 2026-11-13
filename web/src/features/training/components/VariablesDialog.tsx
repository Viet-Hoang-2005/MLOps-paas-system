import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { Placeholder } from "@/shared/components/Placeholder";
import { Search } from "@/shared/components/Search";
import { TextArea } from "@/shared/components/TextArea";
import { PageTabs } from "@/shared/components/PageTabs";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import {
  deleteWorkspaceSecret,
  putWorkspaceSecret,
  updateTrainingWorkspace,
  type TrainingWorkspace,
} from "@/features/training/api/jobWorkspaceApi";

export interface VariablesDialogProps {
  workspace: TrainingWorkspace;
  onRefresh: () => Promise<TrainingWorkspace>;
  onClose: () => void;
  readOnly?: boolean;
}

export function VariablesSecretDialog({
  workspace,
  onRefresh,
  onClose,
  readOnly: forcedReadOnly = false,
}: VariablesDialogProps) {
  const { t } = useTranslation("training");
  const readOnly = forcedReadOnly || workspace.status !== "ready";
  const canRevoke = !readOnly;

  const [activeTab, setActiveTab] = useState<"environment" | "secret">(
    "environment",
  );
  const [busy, setBusy] = useState(false);
  const [searchEnv, setSearchEnv] = useState("");
  const [searchSecret, setSearchSecret] = useState("");

  // Environment sub-dialog state
  const [envModalOpen, setEnvModalOpen] = useState(false);
  const [editingEnvKey, setEditingEnvKey] = useState<string | null>(null);
  const [envFormName, setEnvFormName] = useState("");
  const [envFormValue, setEnvFormValue] = useState("");

  // Secret sub-dialog state
  const [secretModalOpen, setSecretModalOpen] = useState(false);
  const [secretFormName, setSecretFormName] = useState("");
  const [secretFormValue, setSecretFormValue] = useState("");

  async function handleSaveEnvironment() {
    const trimmed = envFormName.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      const next = { ...workspace.environment };
      if (editingEnvKey && editingEnvKey !== trimmed) {
        delete next[editingEnvKey];
      }
      next[trimmed] = envFormValue;
      await updateTrainingWorkspace(workspace.id, workspace.revision, {
        environment: next,
      });
      await onRefresh();
      setEnvModalOpen(false);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteEnvironment(key: string) {
    setBusy(true);
    try {
      const next = { ...workspace.environment };
      delete next[key];
      await updateTrainingWorkspace(workspace.id, workspace.revision, {
        environment: next,
      });
      await onRefresh();
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveSecret() {
    const trimmed = secretFormName.trim();
    if (!trimmed || !secretFormValue) return;
    setBusy(true);
    try {
      await putWorkspaceSecret(
        workspace.id,
        workspace.revision,
        trimmed,
        secretFormValue,
      );
      await onRefresh();
      setSecretModalOpen(false);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteSecret(name: string) {
    setBusy(true);
    try {
      await deleteWorkspaceSecret(workspace.id, workspace.revision, name);
      await onRefresh();
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }

  const envEntries = Object.entries(workspace.environment);
  const secretEntries = workspace.secrets;

  const filteredEnvEntries = envEntries.filter(([key]) =>
    key.toLowerCase().includes(searchEnv.toLowerCase().trim()),
  );

  const filteredSecretEntries = secretEntries.filter((item) =>
    item.name.toLowerCase().includes(searchSecret.toLowerCase().trim()),
  );

  return (
    <>
      <BaseDialog
        title={t("studio.environment")}
        className="flex min-h-120 w-[min(92vw,40rem)] flex-col"
        onClose={onClose}
      >
        <div className="flex flex-1 flex-col space-y-5">
          <PageTabs
            bordered
            tabs={[
              {
                label: t("studio.environmentTitle"),
                isActive: activeTab === "environment",
                onClick: () => setActiveTab("environment"),
              },
              {
                label: t("studio.secretTitle"),
                isActive: activeTab === "secret",
                onClick: () => setActiveTab("secret"),
              },
            ]}
          />

          {activeTab === "environment" && (
            <div className="flex flex-1 flex-col">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1 sm:max-w-xs">
                  <Search
                    value={searchEnv}
                    onChange={(e) => setSearchEnv(e.target.value)}
                    onClear={() => setSearchEnv("")}
                    placeholder={t("studio.searchEnvironment")}
                  />
                </div>
                <Button
                  size="md"
                  variant="primary"
                  icon={<Plus className="h-4 w-4" />}
                  disabled={busy || readOnly}
                  onClick={() => {
                    setEditingEnvKey(null);
                    setEnvFormName("");
                    setEnvFormValue("");
                    setEnvModalOpen(true);
                  }}
                >
                  {t("studio.newEnvironment")}
                </Button>
              </div>

              {envEntries.length === 0 ? (
                <Placeholder
                  className="mt-2"
                  icon={
                    <KeyRound className="h-6 w-6 text-color-muted-foreground" />
                  }
                  title={t("studio.noEnvironmentTitle")}
                  description={t("studio.noEnvironment")}
                />
              ) : filteredEnvEntries.length === 0 ? (
                <p className="py-8 text-center text-style-body text-color-muted-foreground">
                  {t("studio.noMatchingVariables")}
                </p>
              ) : (
                <div className="space-y-3">
                  {filteredEnvEntries.map(([key, text]) => (
                    <div key={key} className="flex items-center gap-2">
                      <div className="min-w-0 flex-1">
                        <Input
                          value={key}
                          readOnly
                          tabIndex={-1}
                          aria-label={key}
                          className="h-10 text-style-body text-color-foreground border-border bg-surface"
                        />
                      </div>
                      <Button
                        size="icon"
                        variant="secondary"
                        className="h-10 w-10 shrink-0"
                        disabled={busy || readOnly}
                        icon={<Pencil className="h-4 w-4" />}
                        aria-label={t("studio.edit")}
                        onClick={() => {
                          setEditingEnvKey(key);
                          setEnvFormName(key);
                          setEnvFormValue(text);
                          setEnvModalOpen(true);
                        }}
                      />
                      <Button
                        size="icon"
                        variant="secondary"
                        className="h-10 w-10 shrink-0"
                        disabled={busy || readOnly}
                        icon={<Trash2 className="h-4 w-4 text-color-danger" />}
                        aria-label={t("studio.delete")}
                        onClick={() => void handleDeleteEnvironment(key)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === "secret" && (
            <div className="flex flex-1 flex-col">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1 sm:max-w-xs">
                  <Search
                    value={searchSecret}
                    onChange={(e) => setSearchSecret(e.target.value)}
                    onClear={() => setSearchSecret("")}
                    placeholder={t("studio.searchSecret")}
                  />
                </div>
                <Button
                  size="md"
                  variant="primary"
                  icon={<Plus className="h-4 w-4" />}
                  disabled={busy || readOnly || !workspace.secrets_available}
                  onClick={() => {
                    setSecretFormName("");
                    setSecretFormValue("");
                    setSecretModalOpen(true);
                  }}
                >
                  {t("studio.newSecret")}
                </Button>
              </div>

              {!workspace.secrets_available && (
                <p className="mb-4 rounded-compact border border-warning/30 bg-warning/10 p-2.5 text-style-caption text-color-warning">
                  {t("studio.secretsUnavailable")}
                </p>
              )}

              {secretEntries.length === 0 ? (
                <Placeholder
                  className="mt-2"
                  icon={
                    <Lock className="h-6 w-6 text-color-muted-foreground" />
                  }
                  title={t("studio.noSecretsTitle")}
                  description={t("studio.noSecrets")}
                />
              ) : filteredSecretEntries.length === 0 ? (
                <p className="py-8 text-center text-style-body text-color-muted-foreground">
                  {t("studio.noMatchingSecrets")}
                </p>
              ) : (
                <div className="space-y-3">
                  {filteredSecretEntries.map((item) => (
                    <div key={item.name} className="flex items-center gap-2">
                      <Button
                        size="icon"
                        variant="secondary"
                        className="h-10 w-10 shrink-0"
                        disabled={busy || !canRevoke}
                        icon={<Trash2 className="h-4 w-4 text-color-danger" />}
                        aria-label={t("studio.delete")}
                        onClick={() => void handleDeleteSecret(item.name)}
                      />
                      <div className="min-w-0 flex-1">
                        <Input
                          value={item.name}
                          readOnly
                          tabIndex={-1}
                          aria-label={item.name}
                          className="h-10 text-style-body text-color-foreground border-border bg-surface"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </BaseDialog>

      {/* Environment Add / Edit Dialog */}
      {envModalOpen && (
        <BaseDialog
          title={
            editingEnvKey
              ? t("studio.editEnvDialogTitle")
              : t("studio.newEnvDialogTitle")
          }
          className="w-[min(92vw,30rem)]"
          onClose={() => setEnvModalOpen(false)}
        >
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSaveEnvironment();
            }}
          >
            <Input
              label={t("studio.key")}
              value={envFormName}
              required
              disabled={busy}
              onChange={(e) => setEnvFormName(e.target.value)}
            />
            <TextArea
              label={t("studio.value")}
              value={envFormValue}
              minHeight="min-h-28"
              onChange={(val) => setEnvFormValue(val)}
            />
            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setEnvModalOpen(false)}
              >
                {t("studio.cancel")}
              </Button>
              <Button
                type="submit"
                loading={busy}
                disabled={!envFormName.trim()}
              >
                {t("studio.save")}
              </Button>
            </div>
          </form>
        </BaseDialog>
      )}

      {/* Secret Add Dialog */}
      {secretModalOpen && (
        <BaseDialog
          title={t("studio.newSecretDialogTitle")}
          className="w-[min(92vw,30rem)]"
          onClose={() => setSecretModalOpen(false)}
        >
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSaveSecret();
            }}
          >
            <Input
              label={t("studio.key")}
              value={secretFormName}
              required
              disabled={busy}
              onChange={(e) => setSecretFormName(e.target.value)}
            />
            <TextArea
              label={t("studio.value")}
              value={secretFormValue}
              required
              minHeight="min-h-28"
              onChange={(val) => setSecretFormValue(val)}
            />
            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setSecretModalOpen(false)}
              >
                {t("studio.cancel")}
              </Button>
              <Button
                type="submit"
                loading={busy}
                disabled={!secretFormName.trim() || !secretFormValue}
              >
                {t("studio.save")}
              </Button>
            </div>
          </form>
        </BaseDialog>
      )}
    </>
  );
}

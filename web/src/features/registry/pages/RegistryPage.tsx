import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Component } from "lucide-react";
import { PageHeader } from "@/shared/components/PageHeader";
import {
  getRegistryFamilies,
  getRegistryVersion,
  getRegistryVersions,
} from "@/features/registry/api/registryApi";
import type {
  RegistryFamily,
  RegistryVersion,
} from "@/features/registry/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/components/toastStore";
import { useTranslation } from "react-i18next";

import { VersionLineage } from "@/features/registry/components/VersionLineage";

import { ModelVersionDetail } from "@/features/registry/components/ModelVersionDetail";

export default function ModelEvolutionPage() {
  const { t } = useTranslation("registry");
  const { familyId } = useParams<{ familyId?: string }>();
  const navigate = useNavigate();

  const [families, setFamilies] = useState<RegistryFamily[]>([]);
  const [loadingFamilies, setLoadingFamilies] = useState(true);

  const [selectedFamily, setSelectedFamily] = useState<RegistryFamily | null>(
    null,
  );
  const [versions, setVersions] = useState<RegistryVersion[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);

  const [selectedVersion, setSelectedVersion] =
    useState<RegistryVersion | null>(null);

  const fetchFamilies = useCallback(async () => {
    try {
      await Promise.resolve();
      setLoadingFamilies(true);
      const data = await getRegistryFamilies();
      setFamilies(data);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("familyLoadFailed")));
    } finally {
      setLoadingFamilies(false);
    }
  }, [t]);

  const fetchVersions = useCallback(
    async (family: RegistryFamily) => {
      try {
        setLoadingVersions(true);
        const data = await getRegistryVersions(family.id);
        setVersions(data);
      } catch (error) {
        toast.error(getApiErrorMessage(error, t("versionsLoadFailed")));
      } finally {
        setLoadingVersions(false);
      }
    },
    [t],
  );

  useEffect(() => {
    queueMicrotask(() => {
      void fetchFamilies();
    });
  }, [fetchFamilies]);

  // Handle URL sync and selection
  useEffect(() => {
    if (loadingFamilies) return;

    if (families.length === 0) {
      queueMicrotask(() => {
        setSelectedFamily(null);
        setVersions([]);
        setSelectedVersion(null);
      });
      return;
    }

    let targetFamily = families[0];
    if (familyId) {
      const found = families.find((f) => f.id.toString() === familyId);
      if (found) targetFamily = found;
    }

    if (targetFamily.id !== selectedFamily?.id) {
      queueMicrotask(() => {
        setSelectedFamily(targetFamily);
        setSelectedVersion(null);
        void fetchVersions(targetFamily);
      });

      // Update URL if we auto-selected
      if (!familyId || familyId !== targetFamily.id.toString()) {
        navigate(`/dashboard/model-evolution/${targetFamily.id}`, {
          replace: true,
        });
      }
    }
  }, [
    families,
    familyId,
    loadingFamilies,
    navigate,
    selectedFamily,
    fetchVersions,
  ]);

  // Auto-select version when versions load
  useEffect(() => {
    if (loadingVersions || versions.length === 0) return;
    if (!selectedVersion) {
      // Pick production, or latest
      const prodVersion = versions.find((v) => v.stage === "production");
      queueMicrotask(() => {
        if (prodVersion) {
          setSelectedVersion(prodVersion);
        } else {
          setSelectedVersion(versions[0]);
        }
      });
    }
  }, [versions, loadingVersions, selectedVersion]);

  useEffect(() => {
    const versionId = selectedVersion?.id;
    if (!versionId) return;

    let cancelled = false;
    const fetchVersionDetail = async () => {
      try {
        const detail = await getRegistryVersion(versionId);
        if (cancelled) return;
        setSelectedVersion(detail);
        setVersions((current) =>
          current.map((item) =>
            item.id === detail.id ? { ...item, ...detail } : item,
          ),
        );
      } catch (error) {
        if (!cancelled) {
          toast.error(getApiErrorMessage(error, t("versionLoadFailed")));
        }
      }
    };

    void fetchVersionDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedVersion?.id, t]);

  const handleActionSuccess = () => {
    // Re-fetch families to update current_production_version
    void fetchFamilies();
    // Re-fetch versions for current family
    if (selectedFamily) {
      void fetchVersions(selectedFamily);
    }
  };

  return (
    <section className="flex w-full flex-1 flex-col space-y-6">
      {/* Header Section */}
      <PageHeader title={t("title")}></PageHeader>

      {/* Main Content Split */}
      <div className="flex flex-col gap-6">
        {/* Top Panel: Version Lineage */}
        <div className="w-full">
          {selectedFamily ? (
            <VersionLineage
              versions={versions}
              selectedVersionId={selectedVersion?.id}
              onSelectVersion={setSelectedVersion}
            />
          ) : (
            <div className="p-8 text-center text-color-muted-foreground text-style-body">
              {t("selectModelFirst", {
                defaultValue: "Select a model to view lineage",
              })}
            </div>
          )}
        </div>

        {/* Bottom Panel: Detail Workspace */}
        <div className="w-full flex flex-col gap-6">
          {selectedFamily ? (
            selectedVersion ? (
              <ModelVersionDetail
                family={selectedFamily}
                version={selectedVersion}
                allVersions={versions}
                onActionSuccess={handleActionSuccess}
              />
            ) : null
          ) : (
            <div className="flex flex-col items-center justify-center p-12 text-center border-2 border-dashed border-border rounded-surface bg-muted/50">
              <div className="rounded-full bg-surface border border-border p-5 mb-5 shadow-sm">
                <Component className="h-10 w-10 text-color-muted-foreground" />
              </div>
              <h3 className="text-style-section-title font-bold text-color-foreground">
                {t("noSelection")}
              </h3>
              <p className="mt-2 text-style-body text-color-muted-foreground max-w-sm">
                {t("noSelectionDescription")}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

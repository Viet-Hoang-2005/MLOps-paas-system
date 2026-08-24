import { FileText, Hammer, Rocket } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Outlet,
  useBlocker,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';

import {
  createProjectMetadata,
  deployBuild,
  getBuild,
  listDeployments,
  startProjectBuild,
  updateProjectMetadata,
} from '@/features/deploy/api/deployApi';
import type { UploadModelContext, UploadStep, UploadTransitionState } from '@/features/deploy/uploadModelContext';
import type { Build, BuildInputForm, Deployment, ProjectMetadataForm } from '@/features/catalog/types';
import { getModelProject } from '@/features/catalog/api/catalogApi';
import { catalogQueryKeys } from '@/features/catalog/queryKeys';
import { getApiErrorMessage } from '@/shared/api/errors';
import { ConfirmModal } from '@/shared/components/ConfirmModal';
import { LineSteps } from '@/shared/components/LineSteps';
import { PageHeader } from '@/shared/components/PageHeader';
import { toast } from '@/shared/components/toastStore';

const managementPath = '/dashboard/management';
const uploadPath = '/dashboard/management/model/upload';

const emptyMetadata: ProjectMetadataForm = {
  name: '',
  description: '',
  access_mode: 'private',
  source_code_file: null,
  reference_data_file: null,
};

const emptyBuild: BuildInputForm = {
  flavor: 'sklearn',
  artifact_format: 'raw',
  source_artifact: null,
  label_mapping_file: null,
  metrics_file: null,
  params_file: null,
  model_insights_file: null,
  feature_importance_file: null,
  input_schema_file: null,
  requirements_text: '',
  requirements_file: null,
};

const fileIdentity = (file: File | null | undefined) => file ? `${file.name}:${file.size}:${file.lastModified}` : '';
const metadataFingerprint = (form: ProjectMetadataForm) => JSON.stringify({
  name: form.name.trim(),
  description: form.description,
  access_mode: form.access_mode,
  source: fileIdentity(form.source_code_file),
  reference: fileIdentity(form.reference_data_file),
});

const hasBuildInput = (form: BuildInputForm) => Boolean(
  form.source_artifact
  || form.requirements_text
  || form.requirements_file
  || form.label_mapping_file
  || form.metrics_file
  || form.params_file
  || form.model_insights_file
  || form.feature_importance_file
  || form.input_schema_file,
);

export default function UploadModelPage() {
  const { t } = useTranslation('deploy');
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedModelId = searchParams.get('modelId');
  const requestedBuildId = searchParams.get('buildId');
  const [project, setProject] = useState<UploadModelContext['project']>(null);
  const [metadataForm, setMetadataForm] = useState<ProjectMetadataForm>(emptyMetadata);
  const [buildForm, setBuildForm] = useState<BuildInputForm>(emptyBuild);
  const [build, setBuild] = useState<Build | null>(null);
  const [deployment, setDeployment] = useState<Deployment | null>(null);
  const [transitionState, setTransitionState] = useState<UploadTransitionState>('idle');
  const [buildChangedSinceSubmission, setBuildChangedSinceSubmission] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [exitRequested, setExitRequested] = useState(false);
  const [metadataBaseline, setMetadataBaseline] = useState(metadataFingerprint(emptyMetadata));
  const allowExit = useRef(false);

  const currentStep: UploadStep = location.pathname.endsWith('/deploy')
    ? 3
    : location.pathname.endsWith('/build')
      ? 2
      : 1;
  const metadataDirty = metadataFingerprint(metadataForm) !== metadataBaseline;
  const buildInputsDirty = build ? buildChangedSinceSubmission : hasBuildInput(buildForm);
  const submittedBuildFailed = build ? ['failed', 'cancelled'].includes(build.status) : false;
  const hasUnsavedBrowserFiles = metadataDirty
    || (hasBuildInput(buildForm) && (!build || submittedBuildFailed))
    || (buildChangedSinceSubmission && build?.status !== 'ready');

  useEffect(() => {
    if (!requestedModelId) {
      if (currentStep !== 1) navigate(`${uploadPath}/metadata`, { replace: true });
      return;
    }
    let active = true;
    getModelProject(requestedModelId)
      .then((result) => {
        if (!active) return;
        setProject(result);
        setMetadataForm((current) => {
          if (metadataFingerprint(current) !== metadataBaseline) return current;
          const next = {
            name: result.name,
            description: result.description,
            access_mode: result.access_mode,
            source_code_file: null,
            reference_data_file: null,
          };
          setMetadataBaseline(metadataFingerprint(next));
          return next;
        });
      })
      .catch((error) => {
        toast.error(getApiErrorMessage(error, t('uploadFlow.messages.metadataLoadFailed')));
        navigate(`${uploadPath}/metadata`, { replace: true });
      });
    return () => { active = false; };
  }, [currentStep, metadataBaseline, navigate, requestedModelId, t]);

  useEffect(() => {
    if (!requestedBuildId) {
      if (currentStep === 3) {
        const suffix = requestedModelId ? `?modelId=${requestedModelId}` : '';
        navigate(`${uploadPath}/build${suffix}`, { replace: true });
      }
      return;
    }
    let active = true;
    Promise.all([getBuild(requestedBuildId), listDeployments()])
      .then(([result, deployments]) => {
        if (!active) return;
        if (requestedModelId && result.project_id !== requestedModelId) throw new Error(t('uploadFlow.messages.buildOwnership'));
        setBuild(result);
        setDeployment(deployments.find((item) => item.build_id === result.id) ?? null);
        setBuildForm((current) => hasBuildInput(current) ? current : {
          ...current,
          flavor: result.flavor,
          artifact_format: result.artifact_format,
          requirements_text: result.requirements_snapshot,
        });
        setBuildChangedSinceSubmission(false);
      })
      .catch((error) => {
        toast.error(getApiErrorMessage(error, t('uploadFlow.messages.buildLoadFailed')));
        const suffix = requestedModelId ? `?modelId=${requestedModelId}` : '';
        navigate(`${uploadPath}/build${suffix}`, { replace: true });
      });
    return () => { active = false; };
  }, [currentStep, navigate, requestedBuildId, requestedModelId, t]);

  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!hasUnsavedBrowserFiles) return;
      event.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasUnsavedBrowserFiles]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) => (
    !allowExit.current
    && hasUnsavedBrowserFiles
    && currentLocation.pathname.startsWith(uploadPath)
    && !nextLocation.pathname.startsWith(uploadPath)
  ));

  const routeFor = useCallback((step: UploadStep, nextProjectId = project?.id, nextBuildId = build?.id) => {
    const route = step === 1 ? 'metadata' : step === 2 ? 'build' : 'deploy';
    const params = new URLSearchParams();
    if (nextProjectId) params.set('modelId', nextProjectId);
    if (step >= 2 && nextBuildId) params.set('buildId', nextBuildId);
    const query = params.toString();
    return `${uploadPath}/${route}${query ? `?${query}` : ''}`;
  }, [build?.id, project?.id]);

  const setMetadataField: UploadModelContext['setMetadataField'] = (field, value) => {
    setMetadataForm((current) => ({ ...current, [field]: value }));
  };

  const setBuildField: UploadModelContext['setBuildField'] = (field, value) => {
    setBuildForm((current) => ({ ...current, [field]: value }));
    if (build) setBuildChangedSinceSubmission(true);
  };

  const continueFromMetadata = useCallback(async () => {
    if (!metadataForm.name.trim()) {
      toast.warning(t('uploadFlow.messages.nameRequired'));
      document.getElementById('metadata-name')?.focus();
      return;
    }
    setTransitionState('saving-metadata');
    try {
      let nextProject = project;
      if (!project) nextProject = await createProjectMetadata(metadataForm);
      else if (metadataDirty) nextProject = await updateProjectMetadata(project.id, metadataForm);
      if (!nextProject) return;
      setProject(nextProject);
      const persistedForm = { ...metadataForm, source_code_file: null, reference_data_file: null };
      setMetadataBaseline(metadataFingerprint(persistedForm));
      setMetadataForm(persistedForm);
      navigate(routeFor(2, nextProject.id));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('uploadFlow.messages.metadataSaveFailed')));
    } finally {
      setTransitionState('idle');
    }
  }, [metadataDirty, metadataForm, navigate, project, routeFor, t]);

  const startBuild = useCallback(async () => {
    if (!project) {
      toast.warning(t('uploadFlow.messages.completeMetadata'));
      navigate(routeFor(1));
      return;
    }
    if (!buildForm.flavor || !buildForm.source_artifact) {
      toast.warning(t('uploadFlow.messages.buildFieldsRequired'));
      return;
    }
    setTransitionState('starting-build');
    try {
      const nextBuild = await startProjectBuild(project.id, buildForm);
      setBuild(nextBuild);
      setDeployment(null);
      setBuildChangedSinceSubmission(false);
      navigate(routeFor(2, project.id, nextBuild.id), { replace: true });
      toast.success(t('uploadFlow.messages.buildStarted'));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('uploadFlow.messages.buildStartFailed')));
    } finally {
      setTransitionState('idle');
    }
  }, [buildForm, navigate, project, routeFor, t]);

  const buildId = build?.id;
  const refreshBuild = useCallback(async () => {
    if (!buildId) return;
    setBuild(await getBuild(buildId));
  }, [buildId]);

  const continueFromBuild = useCallback(() => {
    if (!build || build.status !== 'ready') {
      toast.warning(t('uploadFlow.messages.buildRequired'));
      return;
    }
    if (buildChangedSinceSubmission) {
      toast.warning(t('uploadFlow.messages.rebuildRequired'));
      return;
    }
    navigate(routeFor(3, project?.id, build.id));
  }, [build, buildChangedSinceSubmission, navigate, project?.id, routeFor, t]);

  const deploy = useCallback(async () => {
    if (!build || build.status !== 'ready' || !build.version_id) {
      toast.warning(t('uploadFlow.messages.registeredBuildRequired'));
      return;
    }
    setTransitionState('starting-deployment');
    try {
      const result = await deployBuild(build.id);
      setDeployment(result);
      toast.success(t('uploadFlow.messages.deployStarted'));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('uploadFlow.messages.deployFailed')));
    } finally {
      setTransitionState('idle');
    }
  }, [build, t]);

  const goToStep = useCallback(async (step: UploadStep) => {
    if (transitionState !== 'idle' || step === currentStep) return;
    if (step === 1) {
      navigate(routeFor(1));
      return;
    }
    if (step === 2) {
      if (!project || metadataDirty) await continueFromMetadata();
      else navigate(routeFor(2));
      return;
    }
    if (!project || metadataDirty) {
      await continueFromMetadata();
      toast.warning(t('uploadFlow.messages.completeBuild'));
      return;
    }
    if (!build || build.status !== 'ready' || buildChangedSinceSubmission) {
      toast.warning(t('uploadFlow.messages.completeBuild'));
      navigate(routeFor(2));
      return;
    }
    navigate(routeFor(3));
  }, [build, buildChangedSinceSubmission, continueFromMetadata, currentStep, metadataDirty, navigate, project, routeFor, t, transitionState]);

  const requestExit = () => {
    if (hasUnsavedBrowserFiles) {
      setExitRequested(true);
      setDiscardOpen(true);
    } else navigate(managementPath);
  };

  const handleDeploymentCompleted = useCallback((status: string) => {
    setDeployment((current) => current ? { ...current, status: status as Deployment['status'] } : current);
    if (['healthy', 'unhealthy', 'failed', 'stopped'].includes(status)) {
      void queryClient.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
    }
  }, [queryClient]);

  const context: UploadModelContext = {
    project,
    metadataForm,
    buildForm,
    build,
    deployment,
    metadataDirty,
    buildInputsDirty,
    transitionState,
    setMetadataField,
    setBuildField,
    continueFromMetadata,
    startBuild,
    continueFromBuild,
    deploy,
    goToStep,
    requestExit,
    refreshBuild,
    handleDeploymentCompleted,
  };

  const steps = [
    { id: 1, label: t('uploadFlow.steps.metadata'), icon: FileText },
    { id: 2, label: t('uploadFlow.steps.build'), icon: Hammer },
    { id: 3, label: t('uploadFlow.steps.deploy'), icon: Rocket },
  ];

  return (
    <section className="space-y-6">
      <ConfirmModal
        open={discardOpen || blocker.state === 'blocked'}
        title={t('uploadFlow.discard.title')}
        description={t('uploadFlow.discard.description')}
        tone="danger"
        confirmText={t('uploadFlow.discard.confirm')}
        onConfirm={() => {
          allowExit.current = true;
          setDiscardOpen(false);
          setMetadataForm(emptyMetadata);
          setBuildForm(emptyBuild);
          setBuildChangedSinceSubmission(false);
          if (blocker.state === 'blocked') blocker.proceed();
          else if (exitRequested) navigate(managementPath, { replace: true });
        }}
        onCancel={() => {
          setDiscardOpen(false);
          setExitRequested(false);
          if (blocker.state === 'blocked') blocker.reset();
        }}
      />
      <PageHeader title={t('uploadFlow.title')} />
      <LineSteps
        steps={steps}
        currentStep={currentStep}
        isTransitioning={transitionState !== 'idle'}
        onStepChange={(step) => void goToStep(step as UploadStep)}
      />
      <Outlet context={context} />
    </section>
  );
}

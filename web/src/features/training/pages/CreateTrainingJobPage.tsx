import { Cpu, FileCode2, FileText } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useBlocker, useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import {
  createModelProject,
  getModelProject,
  listModelProjects,
  listReferenceFiles,
  listSourceCodeFiles,
  updateModelProject,
} from '@/features/catalog/api/catalogApi';
import type { ModelProject } from '@/features/catalog/types';
import {
  cancelTrainingJob,
  createTrainingJob,
  getTrainingJob,
  getTrainingRuntimeCapabilities,
} from '@/features/training/api/trainingApi';
import type {
  CreateTrainingJobContext,
  TrainingExecutionForm,
  TrainingMetadataForm,
  TrainingModelMode,
  TrainingSourceForm,
  TrainingStep,
  TrainingTransitionState,
} from '@/features/training/trainingFlowContext';
import type { TrainingJob, TrainingRuntimeCapabilities } from '@/features/training/types';
import { getApiErrorMessage } from '@/shared/api/errors';
import { ConfirmModal } from '@/shared/components/ConfirmModal';
import { LineSteps } from '@/shared/components/LineSteps';
import { PageHeader } from '@/shared/components/PageHeader';
import { toast } from '@/shared/components/toastStore';

const trainingPath = '/dashboard/model-training';
const createPath = `${trainingPath}/create`;

const emptyMetadata: TrainingMetadataForm = { name: '', description: '', access_mode: 'private' };
const emptySource: TrainingSourceForm = {
  model_flavor: 'sklearn',
  entry_point: '',
  requirements_text: '',
};
const emptyExecution: TrainingExecutionForm = {
  vcpu: 2,
  memory_mb: 4096,
  max_runtime_seconds: 3600,
  accelerator_type: 'none',
  accelerator_count: 0,
};

const metadataFingerprint = (form: TrainingMetadataForm) => JSON.stringify({
  name: form.name.trim(),
  description: form.description,
  access_mode: form.access_mode,
});
const sourceFingerprint = (form: TrainingSourceForm) => JSON.stringify({
  model_flavor: form.model_flavor,
  entry_point: form.entry_point.trim(),
  requirements_text: form.requirements_text,
});

export default function CreateTrainingJobPage() {
  const { t } = useTranslation('training');
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedModelId = searchParams.get('modelId');
  const requestedJobId = searchParams.get('jobId');
  const [mode, setModeState] = useState<TrainingModelMode>('new');
  const [projects, setProjects] = useState<ModelProject[]>([]);
  const [project, setProject] = useState<ModelProject | null>(null);
  const [metadataForm, setMetadataForm] = useState(emptyMetadata);
  const [sourceForm, setSourceForm] = useState(emptySource);
  const [executionForm, setExecutionForm] = useState(emptyExecution);
  const [job, setJob] = useState<TrainingJob | null>(null);
  const [capabilities, setCapabilities] = useState<TrainingRuntimeCapabilities | null>(null);
  const [transitionState, setTransitionState] = useState<TrainingTransitionState>('idle');
  const [metadataBaseline, setMetadataBaseline] = useState(metadataFingerprint(emptyMetadata));
  const [sourceBaseline, setSourceBaseline] = useState(sourceFingerprint(emptySource));
  const [codeDirty, setCodeDirty] = useState(false);
  const [dataDirty, setDataDirty] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [exitRequested, setExitRequested] = useState(false);
  const allowExit = useRef(false);

  const currentStep: TrainingStep = location.pathname.endsWith('/execution')
    ? 3
    : location.pathname.endsWith('/source')
      ? 2
      : 1;
  const metadataDirty = metadataFingerprint(metadataForm) !== metadataBaseline;
  const sourceDirty = codeDirty || dataDirty || sourceFingerprint(sourceForm) !== sourceBaseline;
  const hasUnsavedChanges = metadataDirty || sourceDirty;

  const routeFor = useCallback((
    step: TrainingStep,
    projectId: string | null | undefined = project?.id,
    jobId: string | null | undefined = job?.id,
  ) => {
    const route = step === 1 ? 'metadata' : step === 2 ? 'source' : 'execution';
    const params = new URLSearchParams();
    if (projectId) params.set('modelId', projectId);
    if (step === 3 && jobId) params.set('jobId', jobId);
    const query = params.toString();
    return `${createPath}/${route}${query ? `?${query}` : ''}`;
  }, [job?.id, project?.id]);

  useEffect(() => {
    void Promise.all([listModelProjects(), getTrainingRuntimeCapabilities()])
      .then(([projectResponse, runtime]) => {
        setProjects(projectResponse.models);
        setCapabilities(runtime);
        const firstProfile = runtime.cpu_profiles.find((item) => item.id === 'medium') ?? runtime.cpu_profiles[0];
        if (firstProfile) {
          setExecutionForm((current) => ({
            ...current,
            vcpu: firstProfile.vcpu,
            memory_mb: firstProfile.memory_mb,
          }));
        }
      })
      .catch((error) => toast.error(getApiErrorMessage(error, t('createFlow.messages.loadFailed'))));
  }, [t]);

  useEffect(() => {
    if (!requestedModelId) {
      if (currentStep !== 1) navigate(routeFor(1, null, null), { replace: true });
      return;
    }
    let active = true;
    getModelProject(requestedModelId)
      .then((result) => {
        if (!active) return;
        setProject(result);
        setModeState('existing');
        const next = { name: result.name, description: result.description, access_mode: result.access_mode };
        setMetadataForm(next);
        setMetadataBaseline(metadataFingerprint(next));
      })
      .catch((error) => {
        toast.error(getApiErrorMessage(error, t('createFlow.messages.projectLoadFailed')));
        navigate(routeFor(1, null, null), { replace: true });
      });
    return () => { active = false; };
  }, [currentStep, navigate, requestedModelId, routeFor, t]);

  useEffect(() => {
    if (!requestedJobId) return;
    let active = true;
    getTrainingJob(requestedJobId)
      .then((result) => {
        if (!active) return;
        if (requestedModelId && result.project_id !== requestedModelId) throw new Error('Training job project mismatch.');
        setJob(result);
      })
      .catch((error) => toast.error(getApiErrorMessage(error, t('createFlow.messages.jobLoadFailed'))));
    return () => { active = false; };
  }, [requestedJobId, requestedModelId, t]);

  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges) return;
      event.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasUnsavedChanges]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) => (
    !allowExit.current
    && hasUnsavedChanges
    && currentLocation.pathname.startsWith(createPath)
    && !nextLocation.pathname.startsWith(createPath)
  ));

  const selectProject = (projectId: string) => {
    const selected = projects.find((item) => item.id === projectId) ?? null;
    setProject(selected);
    setJob(null);
    setSourceForm(emptySource);
    setSourceBaseline(sourceFingerprint(emptySource));
    setCodeDirty(false);
    setDataDirty(false);
    if (!selected) return;
    const next = { name: selected.name, description: selected.description, access_mode: selected.access_mode };
    setMetadataForm(next);
    setMetadataBaseline(metadataFingerprint(next));
    navigate(routeFor(1, selected.id, undefined), { replace: true });
  };

  const setMode = (nextMode: TrainingModelMode) => {
    setModeState(nextMode);
    setJob(null);
    if (nextMode === 'new') {
      setProject(null);
      setSourceForm(emptySource);
      setSourceBaseline(sourceFingerprint(emptySource));
      setCodeDirty(false);
      setDataDirty(false);
      setMetadataForm(emptyMetadata);
      setMetadataBaseline(metadataFingerprint(emptyMetadata));
      navigate(routeFor(1, null, null), { replace: true });
    }
  };

  const continueFromMetadata = useCallback(async () => {
    if (!metadataForm.name.trim()) {
      toast.warning(t('createFlow.messages.nameRequired'));
      document.getElementById('training-model-name')?.focus();
      return;
    }
    setTransitionState('saving-metadata');
    try {
      let nextProject = project;
      if (!project) {
        nextProject = await createModelProject(metadataForm);
        setProjects((current) => nextProject ? [...current, nextProject] : current);
      } else if (metadataDirty) {
        nextProject = await updateModelProject(project.id, metadataForm);
        setProjects((current) => current.map((item) => item.id === nextProject?.id ? nextProject : item));
      }
      if (!nextProject) return;
      setProject(nextProject);
      const persisted = {
        name: nextProject.name,
        description: nextProject.description,
        access_mode: nextProject.access_mode,
      };
      setMetadataForm(persisted);
      setMetadataBaseline(metadataFingerprint(persisted));
      navigate(routeFor(2, nextProject.id, undefined));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('createFlow.messages.metadataSaveFailed')));
    } finally {
      setTransitionState('idle');
    }
  }, [metadataDirty, metadataForm, navigate, project, routeFor, t]);

  const continueFromSource = useCallback(async (saveEditors: Array<() => Promise<boolean>>) => {
    if (!project) {
      toast.warning(t('createFlow.messages.metadataRequired'));
      navigate(routeFor(1));
      return;
    }
    setTransitionState('saving-source');
    try {
      const saved = await Promise.all(saveEditors.map((save) => save()));
      if (saved.some((value) => !value)) return;
      const [codeFiles, dataFiles] = await Promise.all([
        listSourceCodeFiles(project.id),
        listReferenceFiles(project.id),
      ]);
      const missing = [];
      if (!codeFiles.length) missing.push(t('createFlow.source.sourceCode'));
      if (!dataFiles.length) missing.push(t('createFlow.source.referenceData'));
      const selectedEntryPoint = sourceForm.entry_point.trim();
      if (!selectedEntryPoint || !codeFiles.some((file) => file.relative_path === selectedEntryPoint)) {
        missing.push(t('createFlow.source.entryPoint'));
      }
      if (missing.length) {
        toast.warning(t('createFlow.messages.sourceRequired', { fields: missing.join(', ') }));
        return;
      }
      setCodeDirty(false);
      setDataDirty(false);
      setSourceBaseline(sourceFingerprint(sourceForm));
      navigate(routeFor(3, project.id, undefined));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('createFlow.messages.sourceSaveFailed')));
    } finally {
      setTransitionState('idle');
    }
  }, [navigate, project, routeFor, sourceForm, t]);

  const startTraining = useCallback(async () => {
    if (!project) {
      toast.warning(t('createFlow.messages.metadataRequired'));
      return;
    }
    setTransitionState('starting-training');
    try {
      const nextJob = await createTrainingJob({
        name: `${project.name} training`,
        project_id: project.id,
        model_flavor: sourceForm.model_flavor,
        entry_point: sourceForm.entry_point,
        requirements_text: sourceForm.requirements_text,
        vcpu: executionForm.vcpu,
        memory: executionForm.memory_mb,
        max_runtime_seconds: executionForm.max_runtime_seconds,
        accelerator_type: executionForm.accelerator_type,
        accelerator_count: executionForm.accelerator_count,
        source_zip: null,
        training_data: null,
      });
      setJob(nextJob);
      navigate(routeFor(3, project.id, nextJob.id), { replace: true });
      toast.success(t('createFlow.messages.trainingStarted'));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t('createFlow.messages.trainingStartFailed')));
    } finally {
      setTransitionState('idle');
    }
  }, [executionForm, navigate, project, routeFor, sourceForm, t]);

  const refreshJob = useCallback(async () => {
    if (!job) return;
    setJob(await getTrainingJob(job.id));
  }, [job]);

  const cancelTraining = useCallback(async () => {
    if (!job || !['pending', 'queued', 'uploading', 'running'].includes(job.status)) return;
    setJob(await cancelTrainingJob(job.id));
  }, [job]);

  const finishTraining = () => {
    if (!job) {
      toast.warning(t('createFlow.messages.runFirst'));
      return;
    }
    if (!['completed', 'failed', 'cancelled'].includes(job.status)) {
      toast.warning(t('createFlow.messages.trainingStillRunning'));
      return;
    }
    allowExit.current = true;
    navigate(`${trainingPath}/jobs/${job.id}/details/overview`);
  };

  const goToStep = useCallback(async (step: TrainingStep) => {
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
      toast.warning(t('createFlow.messages.completeSource'));
      return;
    }
    const [codeFiles, dataFiles] = await Promise.all([
      listSourceCodeFiles(project.id),
      listReferenceFiles(project.id),
    ]);
    if (!codeFiles.length || !dataFiles.length || sourceDirty) {
      toast.warning(t('createFlow.messages.completeSource'));
      navigate(routeFor(2));
      return;
    }
    navigate(routeFor(3));
  }, [continueFromMetadata, currentStep, metadataDirty, navigate, project, routeFor, sourceDirty, t, transitionState]);

  const requestExit = () => {
    if (hasUnsavedChanges) {
      setExitRequested(true);
      setDiscardOpen(true);
    } else {
      allowExit.current = true;
      navigate(trainingPath);
    }
  };

  const context: CreateTrainingJobContext = {
    mode,
    projects,
    project,
    metadataForm,
    sourceForm,
    executionForm,
    job,
    capabilities,
    metadataDirty,
    sourceDirty,
    transitionState,
    setMode,
    selectProject,
    setMetadataField: (field, value) => setMetadataForm((current) => ({ ...current, [field]: value })),
    setSourceField: (field, value) => setSourceForm((current) => ({ ...current, [field]: value })),
    setExecutionField: (field, value) => setExecutionForm((current) => ({ ...current, [field]: value })),
    setEditorDirty: (kind, dirty) => kind === 'code' ? setCodeDirty(dirty) : setDataDirty(dirty),
    continueFromMetadata,
    continueFromSource,
    startTraining,
    cancelTraining,
    finishTraining,
    refreshJob,
    goToStep,
    requestExit,
  };

  const steps = [
    { id: 1, label: t('createFlow.steps.metadata'), icon: FileText },
    { id: 2, label: t('createFlow.steps.source'), icon: FileCode2 },
    { id: 3, label: t('createFlow.steps.execution'), icon: Cpu },
  ];

  return (
    <section className="space-y-6">
      <ConfirmModal
        open={discardOpen || blocker.state === 'blocked'}
        title={t('createFlow.discard.title')}
        description={t('createFlow.discard.description')}
        confirmText={t('createFlow.discard.confirm')}
        tone="danger"
        onConfirm={() => {
          allowExit.current = true;
          setDiscardOpen(false);
          if (blocker.state === 'blocked') blocker.proceed();
          else if (exitRequested) navigate(trainingPath, { replace: true });
        }}
        onCancel={() => {
          setDiscardOpen(false);
          setExitRequested(false);
          if (blocker.state === 'blocked') blocker.reset();
        }}
      />
      <PageHeader title={t('createFlow.title')} />
      <LineSteps
        steps={steps}
        currentStep={currentStep}
        isTransitioning={transitionState !== 'idle'}
        onStepChange={(step) => void goToStep(step as TrainingStep)}
      />
      <Outlet context={context} />
    </section>
  );
}

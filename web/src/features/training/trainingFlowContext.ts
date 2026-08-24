import { useOutletContext } from 'react-router-dom';

import type { ModelAccessMode, ModelFlavor, ModelProject } from '@/features/catalog/types';
import type {
  TrainingAcceleratorType,
  TrainingJob,
  TrainingRuntimeCapabilities,
} from '@/features/training/types';

export type TrainingStep = 1 | 2 | 3;
export type TrainingModelMode = 'new' | 'existing';
export type TrainingTransitionState = 'idle' | 'saving-metadata' | 'saving-source' | 'starting-training';

export interface TrainingMetadataForm {
  name: string;
  description: string;
  access_mode: ModelAccessMode;
}

export interface TrainingSourceForm {
  model_flavor: ModelFlavor;
  entry_point: string;
  requirements_text: string;
  requirements_file?: File | null;
}

export interface TrainingExecutionForm {
  vcpu: number;
  memory_mb: number;
  max_runtime_seconds: number;
  accelerator_type: TrainingAcceleratorType;
  accelerator_count: number;
}

export interface CreateTrainingJobContext {
  mode: TrainingModelMode;
  projects: ModelProject[];
  project: ModelProject | null;
  metadataForm: TrainingMetadataForm;
  sourceForm: TrainingSourceForm;
  executionForm: TrainingExecutionForm;
  job: TrainingJob | null;
  capabilities: TrainingRuntimeCapabilities | null;
  metadataDirty: boolean;
  sourceDirty: boolean;
  transitionState: TrainingTransitionState;
  setMode(mode: TrainingModelMode): void;
  selectProject(projectId: string): void;
  setMetadataField<K extends keyof TrainingMetadataForm>(field: K, value: TrainingMetadataForm[K]): void;
  setSourceField<K extends keyof TrainingSourceForm>(field: K, value: TrainingSourceForm[K]): void;
  setExecutionField<K extends keyof TrainingExecutionForm>(field: K, value: TrainingExecutionForm[K]): void;
  setEditorDirty(kind: 'code' | 'data', dirty: boolean): void;
  continueFromMetadata(): Promise<void>;
  continueFromSource(saveEditors: Array<() => Promise<boolean>>): Promise<void>;
  startTraining(): Promise<void>;
  cancelTraining(): Promise<void>;
  finishTraining(): void;
  refreshJob(status?: string): Promise<void>;
  goToStep(step: TrainingStep): Promise<void>;
  requestExit(): void;
}

export const useCreateTrainingJob = () => useOutletContext<CreateTrainingJobContext>();

import { useOutletContext } from 'react-router-dom';

import type {
  Build,
  BuildInputForm,
  Deployment,
  ModelProject,
  ProjectMetadataForm,
} from '@/features/catalog/types';

export type UploadStep = 1 | 2 | 3;
export type UploadTransitionState = 'idle' | 'saving-metadata' | 'starting-build' | 'starting-deployment';

export interface UploadModelContext {
  project: ModelProject | null;
  metadataForm: ProjectMetadataForm;
  buildForm: BuildInputForm;
  build: Build | null;
  deployment: Deployment | null;
  metadataDirty: boolean;
  buildInputsDirty: boolean;
  transitionState: UploadTransitionState;
  setMetadataField: <K extends keyof ProjectMetadataForm>(field: K, value: ProjectMetadataForm[K]) => void;
  setBuildField: <K extends keyof BuildInputForm>(field: K, value: BuildInputForm[K]) => void;
  continueFromMetadata: () => Promise<void>;
  startBuild: () => Promise<void>;
  continueFromBuild: () => void;
  deploy: () => Promise<void>;
  goToStep: (step: UploadStep) => Promise<void>;
  requestExit: () => void;
  refreshBuild: () => Promise<void>;
  handleDeploymentCompleted: (status: string) => void;
}

export const useUploadModel = () => useOutletContext<UploadModelContext>();

export type ResourceId = string;

export type SemanticTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger';

export interface MessageResponse {
  message: string;
}

export interface Paginated<T> {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}

export type RuntimeStatus =
  | 'pending'
  | 'queued'
  | 'building'
  | 'deploying'
  | 'running'
  | 'ready'
  | 'healthy'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'unhealthy'
  | 'stopped'
  | string;

export interface RuntimeLogBatch {
  logs: string[];
  nextOffset: number;
  status: RuntimeStatus;
  error: string;
}

export type RuntimeLogSource =
  | { kind: 'build'; id: ResourceId }
  | { kind: 'deployment'; id: ResourceId }
  | { kind: 'training'; id: ResourceId }
  | { kind: 'drift'; id: ResourceId };

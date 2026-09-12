export interface CaseProgress {
  name: string;
  iteration: number;
  target: number;
  status: "pending" | "running" | "completed" | "timed_out" | "failed";
  exitCode: number | null;
  updatedAt: string | null;
  settings: Record<string, string>;
}

export interface RunProgress {
  attempt: string;
  sourceRevision: string;
  purpose: string;
  done: boolean;
  statusText: string | null;
  cases: CaseProgress[];
}

export interface SimulationJob {
  id: string;
  profile: "poisson-reference" | "poisson-high-voltage";
  title: string;
  purpose: string;
  createdAt: string;
  updatedAt: string;
  sourceRevision: string | null;
  brokerJobId: string | null;
  phase: string;
  submissionState: "preparing" | "submitting" | "submitted" | "failed" | "unknown";
  cluster: "aws-usw2";
  priority: 1;
  nodes: 1;
  gpus: 4 | 8;
  runDirectory: string;
  campaignId: string | null;
  progress: RunProgress | null;
  brokerCheckedAt: string | null;
  progressCheckedAt: string | null;
  brokerError: string | null;
  progressError: string | null;
  launchError: string | null;
  restartCount: number;
  preemptedCount: number;
  brokerMessage: string;
}

export interface JobsResponse {
  jobs: SimulationJob[];
  pollIntervalMs: number;
}

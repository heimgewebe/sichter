export type QueueItem = {
  id: string;
  type?: string;
  mode?: string;
  repo?: string;
  enqueuedAt?: string;
};

export type WorkerStatus = {
  activeState: string;
  subState: string;
  mainPID?: string;
  since?: string | null;
  lastExit?: string | null;
};

export type EventEntry = {
  line?: string;
  ts?: string;
  kind?: string;
  payload?: Record<string, unknown>;
};

export type OverviewResponse = {
  worker: WorkerStatus;
  queue: {
    size: number;
    items: QueueItem[];
  };
  events: EventEntry[];
};

export type RepoStatus = {
  name: string;
  lastEvent?: EventEntry;
};

export type ReposResponse = {
  repos: RepoStatus[];
};

export type RepoFindingsEntry = {
  name: string;
  findingsCount: number;
  findingsBySeverity: Record<string, number>;
  topSeverity: string;
  lastReviewedAt: string | null;
};

export type RepoFindingDetailFile = {
  file: string;
  count: number;
  topSeverity: string;
};

export type RepoFindingDetailItem = {
  severity: string;
  category: string;
  file: string;
  line: number | null;
  message: string;
  evidence?: string | null;
  fixAvailable?: boolean;
  tool?: string | null;
  ruleId?: string | null;
  dedupeKey?: string;
  uncertainty?: Record<string, unknown> | null;
};

export type RepoFindingsResponse = {
  repos: RepoFindingsEntry[];
};

export type RepoFindingDetailResponse = {
  repo: string;
  ts: string | null;
  count: number;
  deduped: number;
  files: RepoFindingDetailFile[];
  items: RepoFindingDetailItem[];
};

export type PolicyResponse = {
  path?: string;
  content?: string;
};

export type TrendPoint = { date: string; findings: number };
export type TrendsResponse = { trends: TrendPoint[] };

export type AlertEntry = {
  repo: string;
  current_count: number;
  baseline_avg: number;
  ratio: number;
  message: string;
};
export type AlertsResponse = { alerts: AlertEntry[]; count: number };

const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') ?? '';

export const withBase = (path: string) => {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  if (API_BASE) {
    return `${API_BASE}${path}`;
  }
  return path;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(withBase(path), {
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API request failed (${res.status})`);
  }
  if (res.status === 204) {
    return {} as T;
  }
  return (await res.json()) as T;
}

export const fetchOverview = () => request<OverviewResponse>('/api/overview');

export const fetchRepos = () => request<ReposResponse>('/api/repos/status');

export const fetchRepoFindings = (n = 200) =>
  request<RepoFindingsResponse>(`/api/repos/findings?n=${n}`);

export type FindingDetailParams = {
  severity?: string[];
  category?: string[];
  sort?: string;
  sortDir?: 'asc' | 'desc';
};

export const fetchRepoFindingDetail = (
  repo: string,
  n = 500,
  params?: FindingDetailParams,
) => {
  const qs = new URLSearchParams();
  qs.set('repo', repo);
  qs.set('n', String(n));
  if (params?.severity?.length) qs.set('severity', params.severity.join(','));
  if (params?.category?.length) qs.set('category', params.category.join(','));
  if (params?.sort) qs.set('sort', params.sort);
  if (params?.sortDir) qs.set('sort_dir', params.sortDir);
  return request<RepoFindingDetailResponse>(`/api/repos/findings/detail?${qs.toString()}`);
};

export const fetchEvents = (limit = 200) =>
  request<{ events: EventEntry[] }>(`/api/events/recent?n=${limit}`);

export const fetchTrends = (days = 30) =>
  request<TrendsResponse>(`/api/metrics/trends?days=${days}`);

export const fetchAlerts = () => request<AlertsResponse>('/api/alerts');

export type ReviewQualityTopRepo = { repo: string; findings: number };
export type ReviewQualityResponse = {
  record_count: number;
  cache_hit_rate: number;
  pr_yield_rate: number;
  avg_tokens_per_finding: number;
  findings_by_severity: Record<string, number>;
  severity_distribution_pct: Record<string, number>;
  top_repos_by_findings: ReviewQualityTopRepo[];
};

export const fetchReviewQuality = (n = 500) =>
  request<ReviewQualityResponse>(`/api/metrics/review-quality?n=${n}`);

export const submitJob = (payload: Record<string, unknown>) =>
  request<{ enqueued: string }>('/api/jobs/submit', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const fetchPolicy = () => request<PolicyResponse>('/api/settings/policy');

export const updatePolicy = (content: Record<string, unknown>) =>
  request<{ written: string }>('/api/settings/policy', {
    method: 'POST',
    body: JSON.stringify(content),
  });

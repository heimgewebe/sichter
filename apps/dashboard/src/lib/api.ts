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

export type PolicyResponse = {
  path?: string;
  content?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') ?? '';

const withBase = (path: string) => {
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

export const fetchEvents = (limit = 200) =>
  request<{ events: EventEntry[] }>(`/api/events/recent?n=${limit}`);

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

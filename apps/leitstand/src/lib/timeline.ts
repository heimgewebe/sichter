import { readFile } from 'fs/promises';
import { join } from 'path';
import { envConfig } from '../config.js';
import { readJsonFile } from '../utils/fs.js';

// ---- Types ----------------------------------------------------------------

export type EventSeverity = 'info' | 'warning' | 'error';

export interface TimelineEvent {
  ts: string;
  kind: string;
  repo: string;
  severity: EventSeverity;
  payload: Record<string, unknown>;
}

export interface TimelineViewData {
  events: TimelineEvent[];
  hoursBack: number;
  isFixture: boolean;
  kinds: string[];
  repos: string[];
}

// ---- Helpers --------------------------------------------------------------

function isTimelineEvent(obj: unknown): obj is TimelineEvent {
  if (!obj || typeof obj !== 'object') return false;
  const e = obj as Record<string, unknown>;
  return (
    typeof e['ts'] === 'string' &&
    typeof e['kind'] === 'string' &&
    typeof e['repo'] === 'string' &&
    typeof e['severity'] === 'string'
  );
}

function filterByAge(events: TimelineEvent[], hoursBack: number): TimelineEvent[] {
  const cutoff = Date.now() - hoursBack * 60 * 60 * 1000;
  // Fixture events are historical; if all would be filtered, return all (fixture mode).
  const filtered = events.filter((e) => new Date(e['ts']).getTime() >= cutoff);
  return filtered.length > 0 ? filtered : events;
}

function sorted(events: TimelineEvent[]): TimelineEvent[] {
  return [...events].sort((a, b) => new Date(b['ts']).getTime() - new Date(a['ts']).getTime());
}

// ---- Loaders --------------------------------------------------------------

async function loadJsonlFile(filePath: string): Promise<TimelineEvent[]> {
  const text = await readFile(filePath, 'utf-8');
  const events: TimelineEvent[] = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const obj = JSON.parse(trimmed);
      if (isTimelineEvent(obj)) events.push(obj);
    } catch {
      // skip malformed lines
    }
  }
  return events;
}

async function tryLoadChronik(hoursBack: number): Promise<TimelineEvent[] | null> {
  if (!envConfig.chronikDir) return null;
  try {
    const { readdir } = await import('fs/promises');
    const files = await readdir(envConfig.chronikDir);
    const jsonlFiles = files.filter((f) => f.endsWith('.jsonl')).sort().reverse();
    const allEvents: TimelineEvent[] = [];
    for (const f of jsonlFiles.slice(0, 12)) {
      const events = await loadJsonlFile(join(envConfig.chronikDir, f));
      allEvents.push(...events);
    }
    if (allEvents.length === 0) return null;
    return filterByAge(sorted(allEvents), hoursBack);
  } catch {
    return null;
  }
}

const FIXTURE_JSONL_PATH = new URL('../../fixtures/events.jsonl', import.meta.url).pathname;
const FIXTURE_JSON_PATH  = new URL('../../fixtures/events.json',  import.meta.url).pathname;

async function loadFixtureEvents(): Promise<TimelineEvent[]> {
  // Try JSONL fixture first, fall back to JSON array
  try {
    return await loadJsonlFile(FIXTURE_JSONL_PATH);
  } catch {
    // fall through
  }
  try {
    const raw = await readJsonFile<unknown[]>(FIXTURE_JSON_PATH);
    return Array.isArray(raw) ? raw.filter(isTimelineEvent) : [];
  } catch {
    return [];
  }
}

// ---- Main controller helper -----------------------------------------------

export async function loadTimelineEvents(hoursBack: number): Promise<{ events: TimelineEvent[]; isFixture: boolean }> {
  // 1. Try chronik directory (real data)
  const chronikEvents = await tryLoadChronik(hoursBack);
  if (chronikEvents) {
    return { events: chronikEvents, isFixture: false };
  }

  // 2. Strict mode: no fixture
  if (envConfig.strictMode) {
    throw new Error('Strict mode: no chronik data available');
  }

  // 3. Fixture fallback
  const fixtureEvents = await loadFixtureEvents();
  return { events: sorted(fixtureEvents), isFixture: true };
}

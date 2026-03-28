import { join } from 'path';
import { envConfig } from '../config.js';
import { readJsonFile } from '../utils/fs.js';

// ---- Types ----------------------------------------------------------------

export interface AnatomyAxis {
  id: string;
  label: string;
  color: string;
}

export interface AnatomyNode {
  id: string;
  label: string;
  axis: string;
  description: string;
}

export type EdgeType = 'data' | 'control' | 'governance';

export interface AnatomyEdge {
  source: string;
  target: string;
  type: EdgeType;
  label: string;
}

export interface AnatomySnapshot {
  schema: string;
  generated: string;
  axes: AnatomyAxis[];
  nodes: AnatomyNode[];
  edges: AnatomyEdge[];
}

export interface AnatomyViewData {
  snapshot: AnatomySnapshot;
  isFixture: boolean;
}

// ---- Structural validation ------------------------------------------------

function validate(raw: unknown): AnatomySnapshot {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Anatomy snapshot must be an object');
  }
  const obj = raw as Record<string, unknown>;
  if (obj['schema'] !== 'anatomy.snapshot.v1') {
    console.warn('[Anatomy] Schema mismatch – expected anatomy.snapshot.v1, got', obj['schema']);
  }
  if (!Array.isArray(obj['nodes']) || !Array.isArray(obj['edges']) || !Array.isArray(obj['axes'])) {
    throw new Error('Anatomy snapshot missing nodes, edges or axes arrays');
  }
  return obj as unknown as AnatomySnapshot;
}

// ---- Loader ---------------------------------------------------------------

const FIXTURE_PATH = new URL('../../fixtures/anatomy.snapshot.json', import.meta.url).pathname;

async function tryLoadArtifact(): Promise<AnatomySnapshot | null> {
  if (!envConfig.artifactDir) return null;
  const artifactPath = join(envConfig.artifactDir, 'anatomy.snapshot.json');
  try {
    const raw = await readJsonFile(artifactPath);
    return validate(raw);
  } catch {
    return null;
  }
}

export async function loadAnatomySnapshot(): Promise<{ snapshot: AnatomySnapshot; isFixture: boolean }> {
  // 1. Try artifact directory (real data)
  const artifact = await tryLoadArtifact();
  if (artifact) {
    return { snapshot: artifact, isFixture: false };
  }

  // 2. Strict mode: refuse to serve fixture
  if (envConfig.strictMode) {
    throw new Error('Strict mode: no anatomy artifact available');
  }

  // 3. Fixture fallback
  const raw = await readJsonFile(FIXTURE_PATH);
  const snapshot = validate(raw);
  return { snapshot, isFixture: true };
}

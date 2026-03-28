import { loadAnatomySnapshot, type AnatomyViewData } from '../lib/anatomy.js';

export async function getAnatomyData(): Promise<AnatomyViewData & Record<string, unknown>> {
  const { snapshot, isFixture } = await loadAnatomySnapshot();
  return {
    snapshot,
    isFixture,
    title: 'Anatomie – Heimgewebe Topologie',
  };
}

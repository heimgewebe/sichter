import { loadTimelineEvents, type TimelineViewData } from '../lib/timeline.js';

export async function getTimelineData(hoursBack: number): Promise<TimelineViewData & Record<string, unknown>> {
  const { events, isFixture } = await loadTimelineEvents(hoursBack);

  const kinds = [...new Set(events.map((e) => e.kind))].sort();
  const repos = [...new Set(events.map((e) => e.repo))].sort();

  return {
    events,
    hoursBack,
    isFixture,
    kinds,
    repos,
    title: 'Zeitachse – Chronologische Event-Timeline',
  };
}

import { useEffect, useMemo, useState } from 'react';

import { AlertEntry, fetchAlerts, fetchOverview, OverviewResponse } from '../lib/api';
import { useEventStream } from '../hooks/useEventStream';

const EVENT_TYPES = ['all', 'sweep', 'findings', 'pr', 'error', 'llm_review', 'autofix', 'heuristics'];

const Overview = () => {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [eventFilter, setEventFilter] = useState('all');
  const { events, connected, error: streamError } = useEventStream('/events/tail');

  useEffect(() => {
    fetchOverview()
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));

    fetchAlerts()
      .then((res) => setAlerts(res.alerts))
      .catch(() => {});
  }, []);

  const filteredEvents = useMemo(() => {
    if (eventFilter === 'all') return events;
    return events.filter((e) => {
      const kind = e.kind ?? (e.payload as Record<string, unknown> | undefined)?.type ?? '';
      return String(kind).includes(eventFilter);
    });
  }, [events, eventFilter]);

  return (
    <div>
      <h2>Overview</h2>
      {error && <p>⚠️ {error}</p>}
      {!data && !error && <p>Lade Dashboard…</p>}
      {alerts.length > 0 && (
        <section style={{ marginBottom: '1.5rem' }}>
          <h3>⚠️ Anomalie-Alerts</h3>
          {alerts.map((a) => (
            <div
              key={a.repo}
              style={{
                background: '#fff3cd',
                borderLeft: '4px solid #f39c12',
                padding: '0.5rem 0.75rem',
                marginBottom: '0.4rem',
                borderRadius: '0.2rem',
                fontSize: '0.875rem',
              }}
            >
              {a.message}
            </div>
          ))}
        </section>
      )}
      {data && (
        <>
          <section className="card-grid">
            <article className="card">
              <h3>Worker</h3>
              <p>
                Status: <strong>{data.worker.activeState}</strong> ({data.worker.subState})
              </p>
              {data.worker.mainPID && <p>PID: {data.worker.mainPID}</p>}
              {data.worker.since && <p>Aktiv seit: {data.worker.since}</p>}
              {data.worker.lastExit && <p>Zuletzt gestoppt: {data.worker.lastExit}</p>}
            </article>
            <article className="card">
              <h3>Queue</h3>
              <p>
                Jobs in Queue: <strong>{data.queue.size}</strong>
              </p>
              <ul>
                {data.queue.items.map((item) => (
                  <li key={item.id}>
                    #{item.id} – {item.type ?? 'Job'} ({item.mode ?? 'mode'}){' '}
                    {item.repo && <span className="badge">{item.repo}</span>}
                  </li>
                ))}
              </ul>
            </article>
            <article className="card">
              <h3>Events</h3>
              <p>WebSocket: {connected ? 'verbunden' : 'polling'}</p>
              <p>Letzte Events: {events.length}</p>
              {streamError && <p>⚠️ {streamError}</p>}
            </article>
          </section>
          <section style={{ marginTop: '2rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0 }}>Event Stream</h3>
              <select
                value={eventFilter}
                onChange={(e) => setEventFilter(e.target.value)}
                style={{ padding: '0.25rem 0.5rem', borderRadius: '0.2rem', fontSize: '0.85rem' }}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <span style={{ fontSize: '0.8rem', color: '#666' }}>
                {filteredEvents.length} / {events.length} Einträge
              </span>
            </div>
            <pre style={{ maxHeight: '360px', overflowY: 'auto', fontSize: '0.78rem', background: '#1e1e1e', color: '#d4d4d4', padding: '0.75rem', borderRadius: '0.25rem' }}>
              {filteredEvents
                .slice()
                .reverse()
                .map((entry) => {
                  const ts = entry.ts ?? '';
                  const kind = entry.kind ?? '';
                  const line = entry.line ?? '';
                  return `${ts} ${kind} ${line}`.trim();
                })
                .join('\n') || '(keine Events)'}
            </pre>
          </section>
        </>
      )}
    </div>
  );
};

export default Overview;

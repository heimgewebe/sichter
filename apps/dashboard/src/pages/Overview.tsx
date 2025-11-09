import { useEffect, useState } from 'react';

import { fetchOverview, OverviewResponse } from '../lib/api';
import { useEventStream } from '../hooks/useEventStream';

const Overview = () => {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { events, connected, error: streamError } = useEventStream('/events/tail');

  useEffect(() => {
    fetchOverview()
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  return (
    <div>
      <h2>Overview</h2>
      {error && <p>⚠️ {error}</p>}
      {!data && !error && <p>Lade Dashboard…</p>}
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
            <h3>Event Stream</h3>
            <pre style={{ maxHeight: '320px', overflowY: 'auto' }}>
              {events
                .slice()
                .reverse()
                .map((entry, idx) => `${entry.ts ?? ''} ${entry.kind ?? ''} ${entry.line ?? ''}`)
                .join('\n')}
            </pre>
          </section>
        </>
      )}
    </div>
  );
};

export default Overview;

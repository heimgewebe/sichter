import { useEffect, useState } from 'react';

import { fetchRepos, submitJob } from '../lib/api';

const Actions = () => {
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [repos, setRepos] = useState<string[]>([]);
  const [selectedRepo, setSelectedRepo] = useState('');
  const [mode, setMode] = useState<'changed' | 'all'>('changed');

  useEffect(() => {
    fetchRepos()
      .then((res) => setRepos(res.repos.map((r) => r.name)))
      .catch(() => {});
  }, []);

  const runJob = async (payload: { type: string; mode: string; repo?: string }) => {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await submitJob({ ...payload, auto_pr: true });
      setFeedback(`✓ Job ${res.enqueued} eingereiht`);
    } catch (err) {
      setFeedback(`⚠️ ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const runCustomJob = () => {
    const payload: { type: string; mode: string; repo?: string } = {
      type: 'ScanChanged',
      mode,
    };
    if (selectedRepo) payload.repo = selectedRepo;
    runJob(payload);
  };

  return (
    <div>
      <h2>Actions</h2>
      <p>Trigger zentrale Sichter-Workflows.</p>

      <section style={{ marginBottom: '1.5rem', padding: '1rem', background: 'var(--card-bg, #f8f9fa)', borderRadius: '0.5rem', border: '1px solid #dee2e6' }}>
        <h3 style={{ marginTop: 0 }}>Job konfigurieren</h3>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
              Repository (optional)
            </label>
            <input
              list="repo-suggestions"
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              placeholder="alle Repos (leer lassen)"
              style={{ padding: '0.4rem 0.6rem', borderRadius: '0.25rem', border: '1px solid #ccc', minWidth: '14rem' }}
            />
            <datalist id="repo-suggestions">
              {repos.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
              Modus
            </label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as 'changed' | 'all')}
              style={{ padding: '0.4rem 0.6rem', borderRadius: '0.25rem', border: '1px solid #ccc' }}
            >
              <option value="changed">changed (nur Änderungen)</option>
              <option value="all">all (vollständiger Scan)</option>
            </select>
          </div>
          <button className="primary" disabled={busy} onClick={runCustomJob}>
            Scan starten
          </button>
        </div>
      </section>

      <h3>Schnellaktionen</h3>
      <div className="button-row">
        <button
          className="primary"
          disabled={busy}
          onClick={() => runJob({ type: 'ScanChanged', mode: 'changed' })}
        >
          Omnicheck (changed)
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => runJob({ type: 'ScanAll', mode: 'all' })}
        >
          Omnicheck (all)
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => runJob({ type: 'PRSweep', mode: 'changed' })}
        >
          Sweep
        </button>
      </div>
      {feedback && (
        <p style={{ marginTop: '1rem', color: feedback.startsWith('✓') ? '#27ae60' : '#c0392b' }}>
          {feedback}
        </p>
      )}
    </div>
  );
};

export default Actions;

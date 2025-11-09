import { useState } from 'react';

import { submitJob } from '../lib/api';

const Actions = () => {
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runJob = async (payload: { type: string; mode: string }) => {
    setBusy(true);
    try {
      const res = await submitJob({ ...payload, auto_pr: true });
      setFeedback(`Job ${res.enqueued} eingereiht`);
    } catch (err) {
      setFeedback((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h2>Actions</h2>
      <p>Trigger zentrale Sichter-Workflows.</p>
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
      {feedback && <p style={{ marginTop: '1rem' }}>{feedback}</p>}
    </div>
  );
};

export default Actions;

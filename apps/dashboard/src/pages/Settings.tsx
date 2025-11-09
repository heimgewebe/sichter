import { FormEvent, useEffect, useState } from 'react';

import { fetchPolicy, updatePolicy } from '../lib/api';

const Settings = () => {
  const [content, setContent] = useState('');
  const [path, setPath] = useState<string | undefined>();
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    fetchPolicy()
      .then((res) => {
        setContent(res.content ?? '');
        setPath(res.path);
      })
      .catch((err) => setStatus((err as Error).message));
  }, []);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const res = await updatePolicy({ raw: content });
      setStatus(`Policy gespeichert nach ${res.written}`);
    } catch (err) {
      setStatus((err as Error).message);
    }
  };

  return (
    <div>
      <h2>Settings</h2>
      {path && <p>Policy-Datei: {path}</p>}
      <form onSubmit={onSubmit}>
        <fieldset>
          <legend>Policy YAML</legend>
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={16}
            style={{ width: '100%', fontFamily: 'monospace' }}
          />
        </fieldset>
        <button className="primary" type="submit" style={{ marginTop: '1rem' }}>
          Speichern
        </button>
      </form>
      {status && <p style={{ marginTop: '1rem' }}>{status}</p>}
    </div>
  );
};

export default Settings;

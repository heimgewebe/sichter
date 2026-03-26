import { useEffect, useState } from 'react';

import { RepoFindingsEntry, RepoStatus, fetchRepoFindings, fetchRepos } from '../lib/api';

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#c0392b',
  error: '#e74c3c',
  warning: '#f39c12',
  info: '#3498db',
  question: '#9b59b6',
  ok: '#27ae60',
};

const severityDot = (sev: string) => {
  const color = SEVERITY_COLOR[sev] ?? '#95a5a6';
  return (
    <span
      title={sev}
      style={{
        display: 'inline-block',
        width: '0.75rem',
        height: '0.75rem',
        borderRadius: '50%',
        backgroundColor: color,
        marginRight: '0.35rem',
        verticalAlign: 'middle',
      }}
    />
  );
};

const Repos = () => {
  const [repos, setRepos] = useState<RepoStatus[]>([]);
  const [findings, setFindings] = useState<Record<string, RepoFindingsEntry>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchRepos(), fetchRepoFindings()])
      .then(([statusRes, findingsRes]) => {
        setRepos(statusRes.repos);
        const map: Record<string, RepoFindingsEntry> = {};
        for (const entry of findingsRes.repos) {
          map[entry.name] = entry;
        }
        setFindings(map);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  return (
    <div>
      <h2>Repositories</h2>
      {error && <p>⚠️ {error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Repository</th>
            <th>Findings</th>
            <th>Severity</th>
            <th>Letztes Event</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {repos.map((repo) => {
            const f = findings[repo.name];
            return (
              <tr key={repo.name}>
                <td>{repo.name}</td>
                <td>{f ? f.findingsCount : '–'}</td>
                <td>
                  {f ? (
                    <>
                      {severityDot(f.topSeverity)}
                      {f.topSeverity}
                    </>
                  ) : (
                    '–'
                  )}
                </td>
                <td>{repo.lastEvent?.kind ?? repo.lastEvent?.line ?? '–'}</td>
                <td>{repo.lastEvent?.ts ?? '–'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default Repos;

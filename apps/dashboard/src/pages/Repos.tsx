import { useEffect, useState } from 'react';

import { RepoStatus, fetchRepos } from '../lib/api';

const Repos = () => {
  const [repos, setRepos] = useState<RepoStatus[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRepos()
      .then((res) => {
        setRepos(res.repos);
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
            <th>Letztes Event</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {repos.map((repo) => (
            <tr key={repo.name}>
              <td>{repo.name}</td>
              <td>{repo.lastEvent?.kind ?? repo.lastEvent?.line ?? '–'}</td>
              <td>{repo.lastEvent?.ts ?? '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Repos;

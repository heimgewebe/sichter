import { useEffect, useMemo, useRef, useState } from 'react';

import {
  RepoFindingDetailResponse,
  RepoFindingsEntry,
  RepoStatus,
  fetchRepoFindingDetail,
  fetchRepoFindings,
  fetchRepos,
} from '../lib/api';

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#c0392b',
  error: '#e74c3c',
  warning: '#f39c12',
  info: '#3498db',
  question: '#9b59b6',
  ok: '#27ae60',
};

const SEVERITY_ORDER = ['critical', 'error', 'warning', 'question', 'info', 'ok'];

const severityRank = (sev: string) => {
  const idx = SEVERITY_ORDER.indexOf(sev);
  return idx === -1 ? 99 : idx;
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
  const [detail, setDetail] = useState<RepoFindingDetailResponse | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const pendingRepoRef = useRef<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<'table' | 'heatmap'>('table');
  const [query, setQuery] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'findings' | 'severity'>('name');
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    fetchRepos()
      .then((statusRes) => {
        setRepos(statusRes.repos);
        setError(null);
        fetchRepoFindings()
          .then((findingsRes) => {
            const map: Record<string, RepoFindingsEntry> = {};
            for (const entry of findingsRes.repos) {
              map[entry.name] = entry;
            }
            setFindings(map);
          })
          .catch(() => {});
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  const toggleSort = (next: 'name' | 'findings' | 'severity') => {
    if (sortBy === next) {
      setSortAsc((v) => !v);
      return;
    }
    setSortBy(next);
    setSortAsc(true);
  };

  const rows = useMemo(() => {
    return [...repos]
      .filter((repo) => repo.name.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => {
        const fa = findings[a.name];
        const fb = findings[b.name];
        let cmp = 0;
        if (sortBy === 'name') {
          cmp = a.name.localeCompare(b.name);
        } else if (sortBy === 'findings') {
          cmp = (fa?.findingsCount ?? 0) - (fb?.findingsCount ?? 0);
        } else {
          cmp = severityRank(fa?.topSeverity ?? 'ok') - severityRank(fb?.topSeverity ?? 'ok');
        }
        return sortAsc ? cmp : -cmp;
      });
  }, [repos, findings, query, sortBy, sortAsc]);

  const loadRepoDetail = async (repoName: string) => {
    setSelectedRepo(repoName);
    setSelectedFile(null);
    setDetail(null);
    pendingRepoRef.current = repoName;
    try {
      const payload = await fetchRepoFindingDetail(repoName);
      if (pendingRepoRef.current === repoName) {
        setDetail(payload);
      }
    } catch {
      if (pendingRepoRef.current === repoName) {
        setDetail({ repo: repoName, count: 0, deduped: 0, files: [], items: [], ts: null });
      }
    }
  };

  const filteredDetailItems = (detail?.items ?? []).filter((item) =>
    selectedFile ? item.file === selectedFile : true,
  );

  return (
    <div>
      <h2>Repositories</h2>
      {error && <p>⚠️ {error}</p>}
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <input
          type="search"
          placeholder="Repo suchen..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ padding: '0.35rem 0.55rem', borderRadius: '0.25rem', border: '1px solid #ccc', minWidth: '12rem' }}
        />
        <button className={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>
          Tabelle
        </button>
        <button className={view === 'heatmap' ? 'primary' : 'secondary'} onClick={() => setView('heatmap')}>
          Heatmap
        </button>
        {view === 'table' && (
          <>
            <button className="secondary" onClick={() => toggleSort('name')}>Sort: Name</button>
            <button className="secondary" onClick={() => toggleSort('findings')}>Sort: Findings</button>
            <button className="secondary" onClick={() => toggleSort('severity')}>Sort: Severity</button>
            <span style={{ fontSize: '0.8rem', color: '#666' }}>{sortAsc ? 'aufsteigend' : 'absteigend'}</span>
          </>
        )}
      </div>

      {view === 'heatmap' ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
          {rows.map((repo) => {
            const f = findings[repo.name];
            const color = SEVERITY_COLOR[f?.topSeverity ?? 'ok'] ?? '#95a5a6';
            return (
              <button
                key={repo.name}
                onClick={() => loadRepoDetail(repo.name)}
                title={`${repo.name}: ${f?.findingsCount ?? 0} Findings`}
                style={{
                  border: 'none',
                  background: color,
                  color: '#fff',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '0.3rem',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                {repo.name} ({f?.findingsCount ?? 0})
              </button>
            );
          })}
          {rows.length === 0 && <p>Keine Repositories gefunden.</p>}
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Repository</th>
              <th>Findings</th>
              <th>Severity</th>
              <th>Letzte Review</th>
              <th>Letztes Event</th>
              <th>Event-Zeit</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((repo) => {
              const f = findings[repo.name];
              return (
                <tr key={repo.name} onClick={() => loadRepoDetail(repo.name)} style={{ cursor: 'pointer' }}>
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
                  <td>{f?.lastReviewedAt ?? '–'}</td>
                  <td>{repo.lastEvent?.kind ?? repo.lastEvent?.line ?? '–'}</td>
                  <td>{repo.lastEvent?.ts ?? '–'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {selectedRepo && detail && (
        <section style={{ marginTop: '1.5rem', padding: '1rem', border: '1px solid #ddd', borderRadius: '0.4rem' }}>
          <h3 style={{ marginTop: 0 }}>Drill-Down: {selectedRepo}</h3>
          <p style={{ marginTop: 0 }}>
            Findings: <strong>{detail.count}</strong> · dedupliziert: <strong>{detail.deduped}</strong>
            {detail.ts ? ` · Stand: ${detail.ts}` : ''}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem' }}>
            <div>
              <h4>Dateien</h4>
              <div style={{ maxHeight: '280px', overflowY: 'auto', border: '1px solid #eee', borderRadius: '0.25rem' }}>
                {(detail.files || []).length === 0 && <p style={{ padding: '0.5rem' }}>Keine Dateidaten verfügbar.</p>}
                {(detail.files || []).map((f) => (
                  <button
                    key={f.file}
                    onClick={() => setSelectedFile(selectedFile === f.file ? null : f.file)}
                    style={{
                      display: 'flex',
                      width: '100%',
                      justifyContent: 'space-between',
                      border: 'none',
                      borderBottom: '1px solid #f1f1f1',
                      background: selectedFile === f.file ? '#eef6ff' : '#fff',
                      padding: '0.4rem 0.5rem',
                      textAlign: 'left',
                      cursor: 'pointer',
                    }}
                  >
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.file}</span>
                    <strong>{f.count}</strong>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <h4>Findings {selectedFile ? `in ${selectedFile}` : ''}</h4>
              <div style={{ maxHeight: '280px', overflowY: 'auto', border: '1px solid #eee', borderRadius: '0.25rem' }}>
                {filteredDetailItems.length === 0 && <p style={{ padding: '0.5rem' }}>Keine Findings verfügbar.</p>}
                {filteredDetailItems.map((item, idx) => (
                  <div key={`${item.file}-${item.line ?? 0}-${idx}`} style={{ padding: '0.5rem', borderBottom: '1px solid #f5f5f5' }}>
                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                      {item.severity} · {item.category} · {item.file}{item.line ? `:${item.line}` : ''}
                      {item.ruleId ? ` · ${item.ruleId}` : ''}
                    </div>
                    <div>{item.message}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default Repos;

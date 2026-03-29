import { useEffect, useState } from 'react';

import { TrendPoint, ReviewQualityResponse, fetchTrends, fetchReviewQuality } from '../lib/api';

const BAR_MAX_HEIGHT = 80; // px

const TrendChart = ({ trends }: { trends: TrendPoint[] }) => {
  if (!trends.length) return <p>Keine Trenddaten.</p>;

  const maxVal = Math.max(...trends.map((t) => t.findings), 1);
  const step = Math.max(1, Math.floor(trends.length / 10));

  return (
    <div style={{ overflowX: 'auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: '2px',
          height: `${BAR_MAX_HEIGHT + 30}px`,
          padding: '0 0.5rem',
        }}
      >
        {trends.map((t, i) => {
          const h = Math.max(2, Math.round((t.findings / maxVal) * BAR_MAX_HEIGHT));
          const showLabel = i % step === 0;
          return (
            <div
              key={t.date}
              title={`${t.date}: ${t.findings} Findings`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                minWidth: '6px',
                flex: 1,
              }}
            >
              <div
                style={{
                  width: '100%',
                  height: `${h}px`,
                  background: t.findings > 0 ? '#e74c3c' : '#27ae60',
                  borderRadius: '2px 2px 0 0',
                  transition: 'height 0.2s',
                }}
              />
              {showLabel && (
                <span
                  style={{
                    fontSize: '0.6rem',
                    color: '#666',
                    marginTop: '2px',
                    whiteSpace: 'nowrap',
                    transform: 'rotate(-45deg)',
                    transformOrigin: 'top left',
                    display: 'block',
                    height: '24px',
                  }}
                >
                  {t.date.slice(5)}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '0.5rem' }}>
        Max: {maxVal} Findings · Zeitraum: {trends[0]?.date} – {trends[trends.length - 1]?.date}
      </div>
    </div>
  );
};

const Metrics = () => {
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quality, setQuality] = useState<ReviewQualityResponse | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);

  const loadTrends = (d: number) => {
    setLoading(true);
    setError(null);
    fetchTrends(d)
      .then((res) => {
        setTrends(res.trends);
        setLoading(false);
      })
      .catch((err) => {
        setError((err as Error).message);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadTrends(days);
  }, [days]);

  useEffect(() => {
    fetchReviewQuality()
      .then(setQuality)
      .catch((err) => setQualityError((err as Error).message));
  }, []);

  const totalFindings = trends.reduce((s, t) => s + t.findings, 0);
  const activeDays = trends.filter((t) => t.findings > 0).length;

  return (
    <div>
      <h2>Metriken &amp; Trends</h2>

      <section style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0 }}>Findings over Time</h3>
          {[7, 14, 30, 90].map((d) => (
            <button
              key={d}
              className={days === d ? 'primary' : 'secondary'}
              onClick={() => setDays(d)}
              style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }}
            >
              {d}d
            </button>
          ))}
        </div>
        {error && <p>⚠️ {error}</p>}
        {loading && <p>Lade…</p>}
        {!loading && !error && <TrendChart trends={trends} />}
        {!loading && !error && (
          <div style={{ display: 'flex', gap: '2rem', marginTop: '0.75rem', fontSize: '0.875rem' }}>
            <span>Gesamt Findings: <strong>{totalFindings}</strong></span>
            <span>Aktive Tage: <strong>{activeDays}</strong> / {trends.length}</span>
          </div>
        )}
      </section>

      <section>
        <h3>Review-Qualität</h3>
        {qualityError && <p>⚠️ {qualityError}</p>}
        {!quality && !qualityError && <p>Lade…</p>}
        {quality && (
          <div>
            <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', marginBottom: '1rem', fontSize: '0.875rem' }}>
              <div>
                <strong>{quality.record_count}</strong>
                <div style={{ color: '#888', fontSize: '0.75rem' }}>Review-Runs</div>
              </div>
              <div>
                <strong>{(quality.cache_hit_rate).toFixed(2)}</strong>
                <div style={{ color: '#888', fontSize: '0.75rem' }}>Ø Cache-Hits / Run</div>
              </div>
              <div>
                <strong>{(quality.pr_yield_rate * 100).toFixed(1)}%</strong>
                <div style={{ color: '#888', fontSize: '0.75rem' }}>PR-Yield (Findings → PRs)</div>
              </div>
              <div>
                <strong>{quality.avg_tokens_per_finding.toFixed(0)}</strong>
                <div style={{ color: '#888', fontSize: '0.75rem' }}>Ø Tokens / Finding</div>
              </div>
            </div>
            {Object.keys(quality.severity_distribution_pct).length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <strong style={{ fontSize: '0.875rem' }}>Severity-Verteilung</strong>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.4rem' }}>
                  {Object.entries(quality.severity_distribution_pct)
                    .sort((a, b) => b[1] - a[1])
                    .map(([sev, pct]) => (
                      <span
                        key={sev}
                        style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          background:
                            sev === 'critical' ? '#c0392b' :
                            sev === 'error' ? '#e74c3c' :
                            sev === 'warning' ? '#e67e22' :
                            '#3498db',
                          color: '#fff',
                        }}
                      >
                        {sev}: {pct}%
                      </span>
                    ))}
                </div>
              </div>
            )}
            {quality.top_repos_by_findings.length > 0 && (
              <div>
                <strong style={{ fontSize: '0.875rem' }}>Top Repos nach Findings</strong>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '0.4rem', fontSize: '0.8rem' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '0.2rem 0.5rem', borderBottom: '1px solid #333' }}>Repo</th>
                      <th style={{ textAlign: 'right', padding: '0.2rem 0.5rem', borderBottom: '1px solid #333' }}>Findings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quality.top_repos_by_findings.map(({ repo, findings }) => (
                      <tr key={repo}>
                        <td style={{ padding: '0.2rem 0.5rem' }}>{repo}</td>
                        <td style={{ textAlign: 'right', padding: '0.2rem 0.5rem' }}>{findings}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
};

export default Metrics;

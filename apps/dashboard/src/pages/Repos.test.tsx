import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchReposMock, fetchRepoFindingsMock, fetchRepoFindingDetailMock } = vi.hoisted(() => ({
  fetchReposMock: vi.fn(),
  fetchRepoFindingsMock: vi.fn(),
  fetchRepoFindingDetailMock: vi.fn(),
}));

vi.mock('../lib/api', () => ({
  fetchRepos: fetchReposMock,
  fetchRepoFindings: fetchRepoFindingsMock,
  fetchRepoFindingDetail: fetchRepoFindingDetailMock,
}));

import Repos from './Repos';

const baseDetail = {
  repo: 'heimgewebe/demo',
  ts: '2026-03-31T06:00:00+00:00',
  count: 2,
  deduped: 2,
  files: [
    { file: 'src/a.py', count: 1, topSeverity: 'error' },
    { file: 'src/b.py', count: 1, topSeverity: 'warning' },
  ],
  items: [
    { severity: 'error', category: 'security', file: 'src/a.py', line: 7, message: 'kept' },
    { severity: 'warning', category: 'style', file: 'src/b.py', line: 3, message: 'other' },
  ],
};

describe('Repos drilldown', () => {
  beforeEach(() => {
    fetchReposMock.mockResolvedValue({ repos: [{ name: 'heimgewebe/demo' }] });
    fetchRepoFindingsMock.mockResolvedValue({
      repos: [
        {
          name: 'heimgewebe/demo',
          findingsCount: 2,
          findingsBySeverity: { error: 1, warning: 1 },
          topSeverity: 'error',
          lastReviewedAt: '2026-03-31T06:00:00+00:00',
        },
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it('keeps the selected file on detail refetch when the file still exists', async () => {
    fetchRepoFindingDetailMock
      .mockResolvedValueOnce(baseDetail)
      .mockResolvedValueOnce({
        ...baseDetail,
        files: [{ file: 'src/a.py', count: 1, topSeverity: 'error' }],
        items: [{ severity: 'error', category: 'security', file: 'src/a.py', line: 7, message: 'kept' }],
      });

    render(
      <MemoryRouter initialEntries={['/repos?repo=heimgewebe%2Fdemo&file=src%2Fa.py']}>
        <Repos />
      </MemoryRouter>,
    );

    await screen.findByRole('heading', { name: 'Findings in src/a.py' });

    fireEvent.click(screen.getByRole('button', { name: 'error' }));

    await waitFor(() =>
      expect(fetchRepoFindingDetailMock).toHaveBeenLastCalledWith('heimgewebe/demo', 500, {
        severity: ['error'],
        sort: 'severity',
        sortDir: 'desc',
      }),
    );
    await screen.findByRole('heading', { name: 'Findings in src/a.py' });
  });

  it('clears the selected file only when the refreshed detail no longer contains it', async () => {
    fetchRepoFindingDetailMock
      .mockResolvedValueOnce(baseDetail)
      .mockResolvedValueOnce({
        ...baseDetail,
        files: [{ file: 'src/b.py', count: 1, topSeverity: 'warning' }],
        items: [{ severity: 'warning', category: 'style', file: 'src/b.py', line: 3, message: 'other' }],
      });

    render(
      <MemoryRouter initialEntries={['/repos?repo=heimgewebe%2Fdemo&file=src%2Fa.py']}>
        <Repos />
      </MemoryRouter>,
    );

    await screen.findByRole('heading', { name: 'Findings in src/a.py' });

    fireEvent.click(screen.getByRole('button', { name: 'warning' }));

    await waitFor(() =>
      expect(fetchRepoFindingDetailMock).toHaveBeenLastCalledWith('heimgewebe/demo', 500, {
        severity: ['warning'],
        sort: 'severity',
        sortDir: 'desc',
      }),
    );
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Findings in src/a.py' })).toBeNull();
    });
    expect(screen.getByRole('heading', { name: 'Findings' })).toBeTruthy();
  });
});
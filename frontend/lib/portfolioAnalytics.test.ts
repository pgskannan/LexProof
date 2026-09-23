import { describe, expect, it } from 'vitest';
import {
  capturePortfolioSnapshotRequest,
  executiveSummaryMetricsPath,
  listPortfolioSnapshotsPath,
} from './portfolioAnalytics';

describe('portfolio analytics request helpers', () => {
  it('builds the snapshot list path with no limit', () => {
    expect(listPortfolioSnapshotsPath('org 1')).toBe('/api/orgs/org%201/portfolio-snapshots');
  });

  it('builds the snapshot list path with an explicit limit', () => {
    expect(listPortfolioSnapshotsPath('org-1', 30)).toBe('/api/orgs/org-1/portfolio-snapshots?limit=30');
  });

  it('builds the capture-snapshot request', () => {
    expect(capturePortfolioSnapshotRequest('org 1')).toEqual({
      path: '/api/orgs/org%201/portfolio-snapshots',
      method: 'POST',
    });
  });

  it('builds the executive-summary metrics path', () => {
    expect(executiveSummaryMetricsPath('org 1')).toBe('/api/orgs/org%201/executive-summary');
  });
});

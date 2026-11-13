import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getApiBaseUrl, fetchHealth } from './health.ts';
import type { HealthResponse } from '../../shared/types.ts';

describe('Frontend Automated Smoke Test', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('resolves the default API base URL when VITE_API_URL is unset', () => {
    const url = getApiBaseUrl();
    expect(url).toBe('http://localhost:8000');
  });

  it('fetches health contract and extracts database value successfully', async () => {
    const mockHealthPayload: HealthResponse = {
      status: 'healthy',
      service: 'ReportSaathi',
      version: '1.0.0',
      database: {
        status: 'connected',
        value: 'Supabase PostgreSQL (users table: 10 rows)',
        message: 'Database query succeeded.',
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockHealthPayload,
    } as Response);

    const { url, data } = await fetchHealth();

    expect(url).toBe('http://localhost:8000/api/health');
    expect(data.status).toBe('healthy');
    expect(data.service).toBe('ReportSaathi');
    expect(data.database?.status).toBe('connected');
    expect(data.database?.value).toBe('Supabase PostgreSQL (users table: 10 rows)');
  });

  it('handles backend connection failure gracefully', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
    } as Response);

    await expect(fetchHealth()).rejects.toThrow('HTTP 503: Service Unavailable');
  });
});

import type { HealthResponse } from '../../shared/types.ts';

export function getApiBaseUrl(): string {
  const metaEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  const envUrl = metaEnv?.VITE_API_URL;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.trim().replace(/\/+$/, '');
  }
  return 'http://localhost:8000';
}

export async function fetchHealth(): Promise<{ url: string; data: HealthResponse }> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/health`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const data: HealthResponse = await response.json();
  return { url, data };
}

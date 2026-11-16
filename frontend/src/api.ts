/**
 * API Client for ReportSaathi Frontend
 * Connects dropzone and actions to FastAPI backend endpoints.
 */

import { getApiBaseUrl } from './health.ts';
import type { LanguageCode, ReportSummary } from '../../shared/types.ts';

export class ApiError extends Error {
  public statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
  }
}

/**
 * Uploads a lab report photo or PDF to POST /api/analyze.
 */
export async function analyzeReport(
  file: File,
  lang: LanguageCode = 'en'
): Promise<ReportSummary> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/analyze`;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('lang', lang);

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      body: formData,
    });
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'Network connection failure.';
    throw new ApiError(`Unable to connect to backend server: ${msg}`, 0);
  }

  if (!response.ok) {
    let detail = `Server responded with HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        detail = errJson.detail;
      }
    } catch {
      // ignore JSON parse failure
    }
    throw new ApiError(detail, response.status);
  }

  const data: ReportSummary = await response.json();
  return data;
}

/**
 * Requests vernacular translation for a report via POST /api/translate.
 */
export async function translateReport(
  reportId: string | undefined,
  lang: LanguageCode,
  summaryEn?: ReportSummary
): Promise<ReportSummary> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/translate`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        report_id: reportId || null,
        summary_en: summaryEn || null,
        lang,
      }),
    });
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'Network connection failure.';
    throw new ApiError(`Unable to connect to translation service: ${msg}`, 0);
  }

  if (!response.ok) {
    let detail = `Translation failed (HTTP ${response.status})`;
    try {
      const errJson = await response.json();
      if (errJson.detail) detail = errJson.detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, response.status);
  }

  const data: ReportSummary = await response.json();
  return data;
}

/**
 * Requests speech audio synthesis stream from POST /api/audio.
 */
export async function fetchAudioBlob(
  summary: ReportSummary,
  lang: LanguageCode
): Promise<Blob> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/audio`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      summary,
      lang,
    }),
  });

  if (!response.ok) {
    throw new ApiError('Failed to synthesize voice note audio.', response.status);
  }

  return response.blob();
}

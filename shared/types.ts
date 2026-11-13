/**
 * Shared Type Definitions for ReportSaathi
 * Single source of truth for Backend (FastAPI) and Frontend (Vite/TS).
 */

export type UrgencyLevel = 'Routine' | 'Consult Soon' | 'Prompt Attention';

export type LanguageCode = 'en' | 'hi' | 'kn';

export type MarkerStatus = 'Normal' | 'Low' | 'High' | 'Borderline';

export interface DatabaseHealth {
  status: 'connected' | 'disconnected' | 'error';
  value: string | null;
  message?: string;
}

export interface HealthResponse {
  status: 'healthy' | 'unhealthy';
  service: string;
  version: string;
  database?: DatabaseHealth;
}

export interface AbnormalMarker {
  test: string;
  value: string;
  status: 'Low' | 'High' | 'Borderline';
  explanation: string;
  trend_note?: string | null;
}

export interface ReportSummary {
  report_id?: string;
  urgency: UrgencyLevel;
  specialist: string;
  normal_summary: string;
  abnormal: AbnormalMarker[];
  cross_marker_patterns: string[];
  doctor_questions: [string, string, string];
  disclaimer: string;
}

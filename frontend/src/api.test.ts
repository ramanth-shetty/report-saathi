/**
 * Integration & Unit Tests for Web Client API & Audio Playback (Task PR-10).
 *
 * Covers:
 * - analyzeReport multipart/form-data POST /api/analyze invocation (FR-2.1).
 * - translateReport POST /api/translate language toggling (FR-5.1).
 * - fetchAudioBlob POST /api/audio in-memory audio fetch (FR-5.2).
 * - HTML5 Web Audio play/pause and 0.8x/1.0x speed controls.
 * - Error handling for network drops, 400 blurry photos, and 500 server errors.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { analyzeReport, translateReport, fetchAudioBlob, ApiError } from './api.ts';
import { ReportSaathiApp } from './main.ts';
import { DISCLAIMER } from '../../shared/constants.ts';
import type { ReportSummary } from '../../shared/types.ts';

function setupDOM(): void {
  document.body.innerHTML = `
    <div id="app" class="container">
      <header class="header">
        <h1 class="logo-title">ReportSaathi</h1>
        <p class="tagline">Family Health Translator</p>
        <div class="pill-group">
          <button id="lang-btn-en" class="lang-pill active" data-lang="en">🇬🇧 English</button>
          <button id="lang-btn-hi" class="lang-pill" data-lang="hi">🇮🇳 हिंदी</button>
          <button id="lang-btn-kn" class="lang-pill" data-lang="kn">🇮🇳 ಕನ್ನಡ</button>
        </div>
      </header>

      <aside id="disclaimer-banner" class="disclaimer-banner">
        <p id="disclaimer-text" class="disclaimer-text"></p>
      </aside>

      <main id="main-content">
        <section id="state-default" class="ui-state state-card active">
          <h2 id="default-title">Upload Lab Report or Medicine Pack</h2>
          <div id="dropzone" class="dropzone"></div>
          <input type="file" id="file-input" class="visually-hidden" />
          <button id="btn-camera" class="btn btn-primary btn-56">Take Photo</button>
          <button id="btn-demo" class="btn btn-secondary btn-56">Preview Demo</button>
        </section>

        <section id="state-empty" class="ui-state state-card" hidden>
          <h2 id="empty-title">No Report Selected</h2>
          <button id="btn-empty-retry" class="btn btn-primary btn-56">Return to Upload</button>
        </section>

        <section id="state-loading" class="ui-state state-card" hidden>
          <h2 id="loading-title">Analyzing Your Report...</h2>
        </section>

        <section id="state-error" class="ui-state state-card" hidden>
          <h2 id="error-title">Could Not Read Report Clearly</h2>
          <p id="error-message" class="error-description"></p>
          <button id="btn-error-retry" class="btn btn-primary btn-56">Try Again</button>
          <button id="btn-error-dismiss" class="btn btn-secondary btn-56">Back</button>
        </section>

        <section id="state-result" class="ui-state state-card" hidden>
          <span id="result-urgency-badge" class="badge">Routine</span>
          <h2 id="result-title">Health Explainer Summary</h2>
          <p id="result-specialist" class="specialist-tag"></p>
          <p id="result-normal-text" class="normal-text"></p>
          <ul id="result-abnormal-list" class="abnormal-list"></ul>
          <ol id="result-questions-list" class="questions-ol"></ol>
          <button id="btn-audio-play" class="btn-play-audio">
            <span class="play-icon">▶️</span>
            <span id="audio-label">Listen</span>
          </button>
          <div class="speed-toggle">
            <button id="speed-08" class="btn-speed">0.8x</button>
            <button id="speed-10" class="btn-speed active">1.0x</button>
          </div>
          <button id="btn-result-reset" class="btn btn-secondary btn-56">Reset</button>
        </section>
      </main>
    </div>
  `;
}

describe('API Client Functions (PR-10)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockSummary: ReportSummary = {
    report_id: 'rep-abc-123',
    urgency: 'Routine',
    specialist: 'General Physician',
    normal_summary: 'All Complete Blood Count tests are normal.',
    abnormal: [],
    cross_marker_patterns: [],
    doctor_questions: ['Q1', 'Q2', 'Q3'],
    disclaimer: DISCLAIMER.en,
  };

  it('analyzeReport successfully posts multipart file to /api/analyze', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSummary,
    } as Response);

    const testFile = new File(['mock content'], 'test.pdf', {
      type: 'application/pdf',
    });
    const result = await analyzeReport(testFile, 'en');

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/analyze',
      expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      })
    );
    expect(result.urgency).toBe('Routine');
    expect(result.report_id).toBe('rep-abc-123');
  });

  it('analyzeReport throws ApiError with backend detail on 400 failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: 'File too blurry or unreadable. Please take a straight-on photo.',
      }),
    } as Response);

    const testFile = new File(['blurry bytes'], 'blurry.jpg', {
      type: 'image/jpeg',
    });
    await expect(analyzeReport(testFile, 'en')).rejects.toThrow(
      'File too blurry or unreadable'
    );
  });

  it('translateReport successfully calls /api/translate', async () => {
    const hindiSummary: ReportSummary = {
      ...mockSummary,
      normal_summary: 'सभी जांचें सामान्य हैं।',
      disclaimer: DISCLAIMER.hi,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => hindiSummary,
    } as Response);

    const result = await translateReport('rep-abc-123', 'hi', mockSummary);

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/translate',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    expect(result.normal_summary).toContain('सभी जांचें सामान्य हैं');
  });

  it('fetchAudioBlob retrieves audio blob from /api/audio', async () => {
    const mockBlob = new Blob(['RIFF_MOCK_BYTES'], { type: 'audio/mpeg' });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => mockBlob,
    } as Response);

    const blob = await fetchAudioBlob(mockSummary, 'en');

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/audio',
      expect.objectContaining({
        method: 'POST',
      })
    );
    expect(blob.type).toBe('audio/mpeg');
  });

  it('fetchAudioBlob throws ApiError on synthesis failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    await expect(fetchAudioBlob(mockSummary, 'kn')).rejects.toThrow(ApiError);
  });
});

describe('Web Client End-to-End API Integration & Audio (PR-10)', () => {
  let app: ReportSaathiApp;

  beforeEach(() => {
    setupDOM();
    vi.restoreAllMocks();

    // Mock HTMLMediaElement play/pause
    window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    window.HTMLMediaElement.prototype.pause = vi.fn();

    // Mock URL.createObjectURL
    global.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-audio-url');

    app = new ReportSaathiApp();
  });

  it('handleFileSelected posts file to backend and displays returned result card', async () => {
    const apiResult: ReportSummary = {
      report_id: 'rep-live-456',
      urgency: 'Consult Soon',
      specialist: 'Diabetologist',
      normal_summary: 'Kidney and liver functions are normal.',
      abnormal: [
        {
          test: 'HbA1c',
          value: '8.2 %',
          status: 'High',
          explanation: '3-month average sugar is higher than standard goal.',
          trend_note: '+0.6 %',
        },
      ],
      cross_marker_patterns: ['Elevated glycated hemoglobin.'],
      doctor_questions: [
        'Should we adjust the diabetes medication?',
        'Do I need to check fasting glucose daily?',
        'When should I repeat the HbA1c test?',
      ],
      disclaimer: DISCLAIMER.en,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => apiResult,
    } as Response);

    const testFile = new File(['fake report pdf'], 'report.pdf', {
      type: 'application/pdf',
    });

    await app.handleFileSelected(testFile);

    expect(app.getCurrentState()).toBe('result');
    expect(app.activeSummary?.report_id).toBe('rep-live-456');

    const specialist = document.getElementById('result-specialist');
    expect(specialist?.textContent).toContain('Diabetologist');

    const abnormal = document.getElementById('result-abnormal-list');
    expect(abnormal?.textContent).toContain('HbA1c');
    expect(abnormal?.textContent).toContain('8.2 %');
  });

  it('handleFileSelected displays friendly error card on backend 400 rejection', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: 'File too blurry or unreadable. Please retake photo.',
      }),
    } as Response);

    const testFile = new File(['blurry'], 'blurry.jpg', {
      type: 'image/jpeg',
    });

    await app.handleFileSelected(testFile);

    expect(app.getCurrentState()).toBe('error');
    const errorEl = document.getElementById('error-message');
    expect(errorEl?.textContent).toContain('File too blurry or unreadable');
  });

  it('switching language in result view translates report dynamically', async () => {
    const englishSummary: ReportSummary = {
      report_id: 'rep-live-456',
      urgency: 'Routine',
      specialist: 'General Physician',
      normal_summary: 'All parameters normal.',
      abnormal: [],
      cross_marker_patterns: [],
      doctor_questions: ['Q1', 'Q2', 'Q3'],
      disclaimer: DISCLAIMER.en,
    };

    const kannadaSummary: ReportSummary = {
      report_id: 'rep-live-456',
      urgency: 'Routine',
      specialist: 'ಸಾಮಾನ್ಯ ವೈದ್ಯರು',
      normal_summary: 'ಎಲ್ಲಾ ಪರೀಕ್ಷೆಗಳು ಸಾಮಾನ್ಯ ಮಿತಿಯಲ್ಲಿದೆ.',
      abnormal: [],
      cross_marker_patterns: [],
      doctor_questions: ['ಪ್ರಶ್ನೆ ೧', 'ಪ್ರಶ್ನೆ ೨', 'ಪ್ರಶ್ನೆ ೩'],
      disclaimer: DISCLAIMER.kn,
    };

    app.activeSummary = englishSummary;
    app.renderReport(englishSummary);
    expect(app.getCurrentState()).toBe('result');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => kannadaSummary,
    } as Response);

    await app.handleLanguageSwitchInResult('kn');

    expect(app.activeSummary.specialist).toBe('ಸಾಮಾನ್ಯ ವೈದ್ಯರು');
    const specialistEl = document.getElementById('result-specialist');
    expect(specialistEl?.textContent).toContain('ಸಾಮಾನ್ಯ ವೈದ್ಯರು');
  });

  it('toggles audio playback on button tap', async () => {
    app.activeSummary = {
      report_id: 'rep-audio-1',
      urgency: 'Routine',
      specialist: 'General Physician',
      normal_summary: 'Normal.',
      abnormal: [],
      cross_marker_patterns: [],
      doctor_questions: ['Q1', 'Q2', 'Q3'],
      disclaimer: DISCLAIMER.en,
    };

    const mockBlob = new Blob(['MOCK_AUDIO'], { type: 'audio/mpeg' });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => mockBlob,
    } as Response);

    await app.toggleAudioPlayback();

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/audio',
      expect.anything()
    );
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it('speed toggle updates playbackRate to 0.8x for older ears', () => {
    const speed08 = document.getElementById('speed-08') as HTMLButtonElement;
    speed08.click();

    expect(app.currentPlaybackSpeed).toBe(0.8);
    expect(speed08.classList.contains('active')).toBe(true);
    expect(speed08.getAttribute('aria-pressed')).toBe('true');
  });
});

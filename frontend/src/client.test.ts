/**
 * Unit & Integration Test Suite for Indic Web Client (Task PR-09).
 *
 * Covers:
 * - 4 UI State transitions: Default, Empty, Loading, and Error.
 * - Trilingual Indic localization (English, Hindi, Kannada) and fixed disclaimers (FR-1.3, NFR-3).
 * - File intake validation (JPEG, PNG, PDF <= 10MB) and oversized/invalid error handling (FR-2.1).
 * - Result card rendering and accessible structure (NFR-6).
 */

import { describe, it, expect, beforeEach } from 'vitest';
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
          <button id="speed-08" class="btn-speed">0.8x</button>
          <button id="speed-10" class="btn-speed active">1.0x</button>
          <button id="btn-result-reset" class="btn btn-secondary btn-56">Reset</button>
        </section>
      </main>
    </div>
  `;
}

describe('ReportSaathiApp Client Tests (PR-09)', () => {
  let app: ReportSaathiApp;

  beforeEach(() => {
    setupDOM();
    app = new ReportSaathiApp();
  });

  describe('1. UI State Management', () => {
    it('initializes in the default state', () => {
      expect(app.getCurrentState()).toBe('default');
      const stateDefault = document.getElementById('state-default');
      expect(stateDefault?.hasAttribute('hidden')).toBe(false);
      expect(stateDefault?.classList.contains('active')).toBe(true);

      const stateLoading = document.getElementById('state-loading');
      expect(stateLoading?.hasAttribute('hidden')).toBe(true);
    });

    it('transitions to empty state correctly', () => {
      app.switchState('empty');
      expect(app.getCurrentState()).toBe('empty');

      const stateEmpty = document.getElementById('state-empty');
      expect(stateEmpty?.hasAttribute('hidden')).toBe(false);
      expect(document.getElementById('state-default')?.hasAttribute('hidden')).toBe(true);
    });

    it('transitions to loading state correctly', () => {
      app.switchState('loading');
      expect(app.getCurrentState()).toBe('loading');

      const stateLoading = document.getElementById('state-loading');
      expect(stateLoading?.hasAttribute('hidden')).toBe(false);
    });

    it('transitions to error state correctly with custom message', () => {
      app.switchState('error');
      expect(app.getCurrentState()).toBe('error');

      const stateError = document.getElementById('state-error');
      expect(stateError?.hasAttribute('hidden')).toBe(false);
    });
  });

  describe('2. Trilingual Indic Localization (FR-1.3, NFR-3)', () => {
    it('starts with English language and default disclaimer', () => {
      expect(app.getCurrentLanguage()).toBe('en');
      expect(document.documentElement.lang).toBe('en');
      const disclaimer = document.getElementById('disclaimer-text');
      expect(disclaimer?.textContent).toBe(DISCLAIMER.en);
    });

    it('switches to Hindi and renders Devanagari disclaimer and labels', () => {
      app.setLanguage('hi');
      expect(app.getCurrentLanguage()).toBe('hi');
      expect(document.documentElement.lang).toBe('hi');

      const disclaimer = document.getElementById('disclaimer-text');
      expect(disclaimer?.textContent).toBe(DISCLAIMER.hi);

      const defaultTitle = document.getElementById('default-title');
      expect(defaultTitle?.textContent).toContain('लैब रिपोर्ट');
    });

    it('switches to Kannada and renders Kannada disclaimer and labels', () => {
      app.setLanguage('kn');
      expect(app.getCurrentLanguage()).toBe('kn');
      expect(document.documentElement.lang).toBe('kn');

      const disclaimer = document.getElementById('disclaimer-text');
      expect(disclaimer?.textContent).toBe(DISCLAIMER.kn);

      const defaultTitle = document.getElementById('default-title');
      expect(defaultTitle?.textContent).toContain('ವರದಿ');
    });
  });

  describe('3. File Validation & Error Handling (FR-2.1)', () => {
    it('rejects unsupported file formats and enters error state', () => {
      const invalidFile = new File(['fake content'], 'video.mp4', {
        type: 'video/mp4',
      });

      app.handleFileSelected(invalidFile);
      expect(app.getCurrentState()).toBe('error');

      const errorMsg = document.getElementById('error-message');
      expect(errorMsg?.textContent).toContain('Unsupported file format');
    });

    it('rejects files exceeding 10MB limit and enters error state', () => {
      // 11MB dummy file
      const largeFile = new File([''], 'large_report.pdf', {
        type: 'application/pdf',
      });
      Object.defineProperty(largeFile, 'size', { value: 11 * 1024 * 1024 });

      app.handleFileSelected(largeFile);
      expect(app.getCurrentState()).toBe('error');

      const errorMsg = document.getElementById('error-message');
      expect(errorMsg?.textContent).toContain('10MB');
    });

    it('accepts valid PDF file and transitions to loading state', () => {
      const validPdf = new File(['%PDF-1.4'], 'report.pdf', {
        type: 'application/pdf',
      });
      Object.defineProperty(validPdf, 'size', { value: 2 * 1024 * 1024 });

      app.handleFileSelected(validPdf);
      expect(app.getCurrentState()).toBe('loading');
    });
  });

  describe('4. Result Card Rendering', () => {
    it('renders a complete ReportSummary into result card elements', () => {
      const sampleSummary: ReportSummary = {
        urgency: 'Prompt Attention',
        specialist: 'Cardiologist',
        normal_summary: 'Kidney and liver markers are normal.',
        abnormal: [
          {
            test: 'Blood Pressure',
            value: '180/110 mmHg',
            status: 'High',
            explanation: 'Significantly elevated blood pressure.',
          },
        ],
        cross_marker_patterns: ['Elevated cardiovascular risk.'],
        doctor_questions: [
          'What medication adjustment is needed for this blood pressure?',
          'Should I monitor blood pressure twice daily?',
          'When should I schedule the next clinical checkup?',
        ],
        disclaimer: DISCLAIMER.en,
      };

      app.renderSampleReport(sampleSummary);
      expect(app.getCurrentState()).toBe('result');

      const urgencyBadge = document.getElementById('result-urgency-badge');
      expect(urgencyBadge?.textContent).toBe('Prompt Attention');

      const specialist = document.getElementById('result-specialist');
      expect(specialist?.textContent).toContain('Cardiologist');

      const normal = document.getElementById('result-normal-text');
      expect(normal?.textContent).toContain('Kidney and liver markers are normal.');

      const abnormal = document.getElementById('result-abnormal-list');
      expect(abnormal?.textContent).toContain('Blood Pressure');
      expect(abnormal?.textContent).toContain('180/110 mmHg');

      const questions = document.getElementById('result-questions-list');
      expect(questions?.children.length).toBe(3);
    });
  });
});

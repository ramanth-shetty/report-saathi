/**
 * ReportSaathi Accessible Indic Web Client
 * Implements 4 UI states, trilingual Indic switching, and file intake.
 */

import { DISCLAIMER } from '../../shared/constants.ts';
import type { LanguageCode, ReportSummary } from '../../shared/types.ts';

export type UIState = 'default' | 'empty' | 'loading' | 'error' | 'result';

// Trilingual UI strings (Hindi in respectful 'आप' register; Kannada in respectful 'ನೀವು' register)
export const UI_STRINGS: Record<LanguageCode, {
  tagline: string;
  defaultTitle: string;
  defaultSubtitle: string;
  chipMemory: string;
  chipExplain: string;
  chipDpdp: string;
  dropPrompt: string;
  dropHint: string;
  btnCamera: string;
  btnDemo: string;
  emptyTitle: string;
  emptyDesc: string;
  btnReturn: string;
  loadingTitle: string;
  loadingSubtitle: string;
  step1: string;
  step2: string;
  step3: string;
  step4: string;
  reassurance: string;
  errorHeading: string;
  btnRetry: string;
  btnHome: string;
  resultTitle: string;
  normalTitle: string;
  notableTitle: string;
  questionsTitle: string;
  btnUploadAnother: string;
  audioLabel: string;
}> = {
  en: {
    tagline: 'Family Health Translator • Simple & Private',
    defaultTitle: 'Upload Lab Report or Medicine Pack',
    defaultSubtitle: 'Take a straight-on photo or upload a PDF. No typing required.',
    chipMemory: 'Personal details removed in memory',
    chipExplain: 'Explains simply, does not diagnose',
    chipDpdp: 'DPDP Act 2023 compliant',
    dropPrompt: 'Drag and drop report photo or PDF here',
    dropHint: 'Supports JPEG, PNG, PDF up to 10MB',
    btnCamera: '📸 Take Photo / Choose File',
    btnDemo: 'Preview Sample Report Card',
    emptyTitle: 'No Report Selected',
    emptyDesc: 'Please place a medicine blister strip or a printed lab report flat on a table under good lighting.',
    btnReturn: 'Return to Upload',
    loadingTitle: 'Analyzing Your Report...',
    loadingSubtitle: 'Please wait 15–20 seconds • Best-effort local privacy scrub',
    step1: 'Personal identity details scrubbed locally in RAM',
    step2: 'Extracting lab biomarkers with OCR...',
    step3: 'Translating medical terminology into plain Indic words',
    step4: 'Formulating 3 practical questions for your doctor',
    reassurance: 'Your report image is processed in RAM and never written to disk.',
    errorHeading: 'Could Not Read Report Clearly',
    btnRetry: '🔄 Try Again / Retake Photo',
    btnHome: 'Back to Home',
    resultTitle: 'Health Explainer Summary',
    normalTitle: 'Normal Parameters',
    notableTitle: 'Notable Biomarkers',
    questionsTitle: 'Questions to Ask Your Doctor',
    btnUploadAnother: '📄 Upload Another Report',
    audioLabel: 'Listen in English (0:40)',
  },
  hi: {
    tagline: 'फैमिली हेल्थ ट्रांसलेटर • आपकी भाषा में सरल और सुरक्षित',
    defaultTitle: 'लैब रिपोर्ट या दवा का पैकेट अपलोड करें',
    defaultSubtitle: 'सीधा फोटो लें या पीडीएफ चुनें। कुछ भी लिखने की जरूरत नहीं।',
    chipMemory: 'निजी पहचान तुरंत मेमोरी में हटा दी जाती है',
    chipExplain: 'सरल व्याख्या करता है, बीमारी घोषित नहीं करता',
    chipDpdp: 'डीपीडीपी अधिनियम 2023 के अनुरूप सुरक्षित',
    dropPrompt: 'रिपोर्ट का फोटो या पीडीएफ यहां खींचें या चुनें',
    dropHint: 'जेपीईजी, पीएनजी और पीडीएफ (अधिकतम 10 एमबी)',
    btnCamera: '📸 फोटो लें / फाइल चुनें',
    btnDemo: 'नमूना रिपोर्ट देखें',
    emptyTitle: 'कोई रिपोर्ट नहीं चुनी गई',
    emptyDesc: 'कृपया दवा का पत्ता या रिपोर्ट अच्छी रोशनी में सीधी रखकर फोटो लें।',
    btnReturn: 'वापस अपलोड पर जाएं',
    loadingTitle: 'आपकी रिपोर्ट का विश्लेषण हो रहा है...',
    loadingSubtitle: 'कृपया 15–20 सेकंड प्रतीक्षा करें • गोपनीयता सुरक्षित',
    step1: 'निजी विवरण मेमोरी में हटा दिए गए हैं',
    step2: 'जांच के नंबर पहचाने जा रहे हैं...',
    step3: 'कठिन शब्दों को सरल हिंदी में बदला जा रहा है',
    step4: 'डॉक्टर से पूछने योग्य 3 सवाल तैयार किए जा रहे हैं',
    reassurance: 'आपकी फोटो केवल मेमोरी में प्रोसेस होती है, डिस्क पर नहीं रखी जाती।',
    errorHeading: 'रिपोर्ट साफ नहीं पढ़ी जा सकी',
    btnRetry: '🔄 दोबारा फोटो लें / प्रयास करें',
    btnHome: 'शुरुआत पर लौटें',
    resultTitle: 'रिपोर्ट का सरल विवरण',
    normalTitle: 'सामान्य जांचें',
    notableTitle: 'ध्यान देने योग्य जांचें',
    questionsTitle: 'डॉक्टर साहब से पूछने के सवाल',
    btnUploadAnother: '📄 दूसरी रिपोर्ट अपलोड करें',
    audioLabel: 'हिंदी में सुनें (0:40)',
  },
  kn: {
    tagline: 'ವರದಿ ಸಾಥಿ • ಸರಳ ಕನ್ನಡದಲ್ಲಿ ನಿಮ್ಮ ಕುಟುಂಬದ ಆರೋಗ್ಯ ವಿವರಣೆ',
    defaultTitle: 'ಲ್ಯಾಬ್ ವರದಿ ಅಥವಾ ಔಷಧಿ ಪ್ಯಾಕ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',
    defaultSubtitle: 'ನೇರವಾದ ಫೋಟೋ ತೆಗೆದುಕೊಳ್ಳಿ ಅಥವಾ ಪಿಡಿಎಫ್ ಆಯ್ಕೆಮಾಡಿ. ಟೈಪ್ ಮಾಡುವ ಅಗತ್ಯವಿಲ್ಲ.',
    chipMemory: 'ವೈಯಕ್ತಿಕ ವಿವರಗಳನ್ನು ಸ್ಥಳೀಯವಾಗಿ ತೆಗೆದುಹಾಕಲಾಗುತ್ತದೆ',
    chipExplain: 'ಸರಳವಾಗಿ ವಿವರಿಸುತ್ತದೆ, ರೋಗನಿರ್ಣಯ ಮಾಡುವುದಿಲ್ಲ',
    chipDpdp: 'ಡಿಪಿಡಿಪಿ ಕಾಯ್ದೆ 2023 ಕ್ಕೆ ಬದ್ಧವಾಗಿದೆ',
    dropPrompt: 'ವರದಿಯ ಫೋಟೋ ಅಥವಾ ಪಿಡಿಎಫ್ ಅನ್ನು ಇಲ್ಲಿ ಹಾಕಿ',
    dropHint: 'ಜೆಪಿಇಜಿ, ಪಿಎನ್‌ಜಿ ಮತ್ತು ಪಿಡಿಎಫ್ (ಗರಿಷ್ಠ 10 ಎಂಬಿ)',
    btnCamera: '📸 ಫೋಟೋ ತೆಗೆಯಿರಿ / ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ',
    btnDemo: 'ಮಾದರಿ ವರದಿ ಕಾರ್ಡ್ ವೀಕ್ಷಿಸಿ',
    emptyTitle: 'ಯಾವುದೇ ವರದಿ ಆಯ್ಕೆಯಾಗಿಲ್ಲ',
    emptyDesc: 'ದಯವಿಟ್ಟು ಔಷಧಿ ಪಟ್ಟಿ ಅಥವಾ ಮುದ್ರಿತ ವರದಿಯನ್ನು ಬೆಳಕಿನಲ್ಲಿ ಸಮತಟ್ಟಾಗಿ ಇಟ್ಟು ಫೋಟೋ ತೆಗೆಯಿರಿ.',
    btnReturn: 'ಅಪ್‌ಲೋಡ್‌ಗೆ ಹಿಂತಿರುಗಿ',
    loadingTitle: 'ನಿಮ್ಮ ವರದಿಯನ್ನು ವಿಶ್ಲೇಷಿಸಲಾಗುತ್ತಿದೆ...',
    loadingSubtitle: 'ದಯವಿಟ್ಟು 15–20 ಸೆಕೆಂಡು ಕಾಯಿರಿ • ಸಂಪೂರ್ಣ ಗೌಪ್ಯತೆ',
    step1: 'ವೈಯಕ್ತಿಕ ಗುರುತುಗಳನ್ನು ಮೆಮೊರಿಯಲ್ಲಿ ಅಳಿಸಲಾಗಿದೆ',
    step2: 'ವರದಿಯ ಮೌಲ್ಯಗಳನ್ನು ಓದಲಾಗುತ್ತಿದೆ...',
    step3: 'ವೈದ್ಯಕೀಯ ಪದಗಳನ್ನು ಸರಳ ಕನ್ನಡಕ್ಕೆ ಬದಲಾಯಿಸಲಾಗುತ್ತಿದೆ',
    step4: 'ವೈದ್ಯರನ್ನು ಕೇಳಲು 3 ಉಪಯುಕ್ತ ಪ್ರಶ್ನೆಗಳನ್ನು ಸಿದ್ಧಪಡಿಸಲಾಗುತ್ತಿದೆ',
    reassurance: 'ನಿಮ್ಮ ಚಿತ್ರವನ್ನು ಕೇವಲ ಮೆಮೊರಿಯಲ್ಲಿ ಸಂಸ್ಕರಿಸಲಾಗುತ್ತದೆ, ಡಿಸ್ಕ್‌ನಲ್ಲಿ ಉಳಿಸುವುದಿಲ್ಲ.',
    errorHeading: 'ವರದಿಯನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ಓದಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ',
    btnRetry: '🔄 ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ',
    btnHome: 'ಮೊದಲ ಪುಟಕ್ಕೆ ಹೋಗಿ',
    resultTitle: 'ಆರೋಗ್ಯ ವರದಿ ಸಾರಾಂಶ',
    normalTitle: 'ಸಾಮಾನ್ಯ ಪರೀಕ್ಷೆಗಳು',
    notableTitle: 'ಮುಖ್ಯ ಬದಲಾವಣೆಗಳು',
    questionsTitle: 'ವೈದ್ಯರನ್ನು ಕೇಳಬೇಕಾದ ಪ್ರಶ್ನೆಗಳು',
    btnUploadAnother: '📄 ಇನ್ನೊಂದು ವರದಿ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',
    audioLabel: 'ಕನ್ನಡದಲ್ಲಿ ಆಲಿಸಿ (0:40)',
  },
};

export class ReportSaathiApp {
  private currentLang: LanguageCode = 'en';
  private currentState: UIState = 'default';

  // DOM Elements
  private stateDefault!: HTMLElement;
  private stateEmpty!: HTMLElement;
  private stateLoading!: HTMLElement;
  private stateError!: HTMLElement;
  private stateResult!: HTMLElement;
  private disclaimerText!: HTMLElement;
  private fileInput!: HTMLInputElement;
  private dropzone!: HTMLElement;
  private errorMessage!: HTMLElement;

  constructor() {
    this.initElements();
    this.bindEvents();
    this.setLanguage('en');
    this.switchState('default');
  }

  private initElements(): void {
    this.stateDefault = document.getElementById('state-default') as HTMLElement;
    this.stateEmpty = document.getElementById('state-empty') as HTMLElement;
    this.stateLoading = document.getElementById('state-loading') as HTMLElement;
    this.stateError = document.getElementById('state-error') as HTMLElement;
    this.stateResult = document.getElementById('state-result') as HTMLElement;
    this.disclaimerText = document.getElementById('disclaimer-text') as HTMLElement;
    this.fileInput = document.getElementById('file-input') as HTMLInputElement;
    this.dropzone = document.getElementById('dropzone') as HTMLElement;
    this.errorMessage = document.getElementById('error-message') as HTMLElement;
  }

  private bindEvents(): void {
    // Language selection pills
    const langButtons = document.querySelectorAll<HTMLButtonElement>('.lang-pill');
    langButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const lang = btn.getAttribute('data-lang') as LanguageCode;
        if (lang) {
          this.setLanguage(lang);
        }
      });
    });

    // File input trigger
    const btnCamera = document.getElementById('btn-camera');
    btnCamera?.addEventListener('click', () => {
      this.fileInput.click();
    });

    this.dropzone?.addEventListener('click', () => {
      this.fileInput.click();
    });

    this.dropzone?.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.fileInput.click();
      }
    });

    // Drag and Drop
    this.dropzone?.addEventListener('dragover', (e: DragEvent) => {
      e.preventDefault();
      this.dropzone.classList.add('dragover');
    });

    this.dropzone?.addEventListener('dragleave', () => {
      this.dropzone.classList.remove('dragover');
    });

    this.dropzone?.addEventListener('drop', (e: DragEvent) => {
      e.preventDefault();
      this.dropzone.classList.remove('dragover');
      if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        this.handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    this.fileInput?.addEventListener('change', () => {
      if (this.fileInput.files && this.fileInput.files.length > 0) {
        this.handleFileSelected(this.fileInput.files[0]);
      } else {
        this.switchState('empty');
      }
    });

    // Empty and Error retry buttons
    document.getElementById('btn-empty-retry')?.addEventListener('click', () => {
      this.switchState('default');
    });

    document.getElementById('btn-error-retry')?.addEventListener('click', () => {
      this.fileInput.value = '';
      this.fileInput.click();
    });

    document.getElementById('btn-error-dismiss')?.addEventListener('click', () => {
      this.switchState('default');
    });

    // Demo / Sample preview button
    document.getElementById('btn-demo')?.addEventListener('click', () => {
      this.renderSampleReport();
    });

    document.getElementById('btn-result-reset')?.addEventListener('click', () => {
      this.fileInput.value = '';
      this.switchState('default');
    });

    // Audio Playback simulation & speed toggles
    this.bindAudioControls();
  }

  private bindAudioControls(): void {
    const playBtn = document.getElementById('btn-audio-play');
    let isPlaying = false;
    playBtn?.addEventListener('click', () => {
      isPlaying = !isPlaying;
      const playIcon = playBtn.querySelector('.play-icon');
      if (playIcon) {
        playIcon.textContent = isPlaying ? '⏸️' : '▶️';
      }
    });

    const speed08 = document.getElementById('speed-08') as HTMLButtonElement | null;
    const speed10 = document.getElementById('speed-10') as HTMLButtonElement | null;

    speed08?.addEventListener('click', () => {
      speed08.classList.add('active');
      speed08.setAttribute('aria-pressed', 'true');
      speed10?.classList.remove('active');
      speed10?.setAttribute('aria-pressed', 'false');
    });

    speed10?.addEventListener('click', () => {
      speed10.classList.add('active');
      speed10.setAttribute('aria-pressed', 'true');
      speed08?.classList.remove('active');
      speed08?.setAttribute('aria-pressed', 'false');
    });
  }

  public setLanguage(lang: LanguageCode): void {
    this.currentLang = lang;
    document.documentElement.lang = lang;

    // Update Language Pills UI
    document.querySelectorAll<HTMLButtonElement>('.lang-pill').forEach((btn) => {
      const match = btn.getAttribute('data-lang') === lang;
      btn.classList.toggle('active', match);
      btn.setAttribute('aria-checked', match ? 'true' : 'false');
    });

    // Update Invariant Fixed Disclaimer
    this.disclaimerText.textContent = DISCLAIMER[lang];

    // Update Dynamic UI text from dictionary
    const strings = UI_STRINGS[lang];
    const setText = (id: string, text: string) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    setText('default-title', strings.defaultTitle);
    setText('empty-title', strings.emptyTitle);
    setText('loading-title', strings.loadingTitle);
    setText('error-title', strings.errorHeading);
    setText('result-title', strings.resultTitle);
    setText('audio-label', strings.audioLabel);

    const btnCamera = document.getElementById('btn-camera');
    if (btnCamera) {
      btnCamera.innerHTML = `<span class="btn-icon" aria-hidden="true">📸</span><span>${strings.btnCamera}</span>`;
    }
  }

  public switchState(state: UIState): void {
    this.currentState = state;

    const allStates: Record<UIState, HTMLElement> = {
      default: this.stateDefault,
      empty: this.stateEmpty,
      loading: this.stateLoading,
      error: this.stateError,
      result: this.stateResult,
    };

    (Object.keys(allStates) as UIState[]).forEach((s) => {
      const el = allStates[s];
      if (el) {
        if (s === state) {
          el.removeAttribute('hidden');
          el.classList.add('active');
        } else {
          el.setAttribute('hidden', '');
          el.classList.remove('active');
        }
      }
    });
  }

  public handleFileSelected(file: File): void {
    const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
    const maxSize = 10 * 1024 * 1024; // 10MB

    if (!validTypes.includes(file.type)) {
      this.errorMessage.textContent = 'Unsupported file format. Please upload a JPEG photo, PNG image, or PDF document.';
      this.switchState('error');
      return;
    }

    if (file.size > maxSize) {
      this.errorMessage.textContent = 'File exceeds maximum allowed size of 10MB. Please choose a smaller file.';
      this.switchState('error');
      return;
    }

    // Enter Loading State with animated progress
    this.switchState('loading');

    // Simulate analysis completion into Result view (wire-ready for PR-10 API integration)
    setTimeout(() => {
      this.renderSampleReport();
    }, 1200);
  }

  public renderSampleReport(sample?: ReportSummary): void {
    const data: ReportSummary = sample || {
      urgency: 'Routine',
      specialist: 'General Physician',
      normal_summary: 'All basic blood counts, liver enzymes, and renal markers are within standard intervals.',
      abnormal: [
        {
          test: 'Fasting Blood Sugar',
          value: '142 mg/dL',
          status: 'High',
          explanation: 'Slightly above normal fasting glucose range (70–100 mg/dL). Discuss with your doctor.',
          trend_note: '+12 mg/dL',
        },
      ],
      cross_marker_patterns: ['Isolated fasting glucose elevation.'],
      doctor_questions: [
        'Should I schedule an annual HbA1c test to assess 3-month glycemic control?',
        'Are any dietary or exercise adjustments recommended based on this report?',
        'When should I schedule my next routine blood glucose follow-up?',
      ],
      disclaimer: DISCLAIMER[this.currentLang],
    };

    const urgencyBadge = document.getElementById('result-urgency-badge');
    if (urgencyBadge) {
      urgencyBadge.textContent = data.urgency;
      urgencyBadge.className = `badge badge-${data.urgency.toLowerCase().replace(' ', '-')}`;
    }

    const specialistTag = document.getElementById('result-specialist');
    if (specialistTag) {
      specialistTag.textContent = `Recommended Specialist: ${data.specialist}`;
    }

    const normalText = document.getElementById('result-normal-text');
    if (normalText) {
      normalText.textContent = data.normal_summary;
    }

    const abnormalList = document.getElementById('result-abnormal-list');
    if (abnormalList) {
      abnormalList.innerHTML = data.abnormal
        .map(
          (m) => `
        <li class="marker-item">
          <div class="marker-top">
            <span class="marker-name">${m.test}</span>
            <span class="badge badge-warning">${m.value} [${m.status}]</span>
          </div>
          <p class="marker-explanation">${m.explanation}</p>
        </li>
      `
        )
        .join('');
    }

    const questionsList = document.getElementById('result-questions-list');
    if (questionsList) {
      questionsList.innerHTML = data.doctor_questions
        .map((q) => `<li>${q}</li>`)
        .join('');
    }

    this.switchState('result');
  }

  public getCurrentLanguage(): LanguageCode {
    return this.currentLang;
  }

  public getCurrentState(): UIState {
    return this.currentState;
  }
}

// Bootstrap app on DOM ready
let appInstance: ReportSaathiApp | null = null;
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    appInstance = new ReportSaathiApp();
  });
}

export { appInstance };

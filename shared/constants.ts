/**
 * Shared Constants for ReportSaathi
 */

export const SERVICE_NAME = 'ReportSaathi';
export const SERVICE_VERSION = '1.0.0';

export const SUPPORTED_LANGUAGES = ['en', 'hi', 'kn'] as const;

export const URGENCY_LEVELS = [
  'Routine',
  'Consult Soon',
  'Prompt Attention',
] as const;

export const DISCLAIMER = {
  en: 'This explains your report in simple words. It is not a diagnosis. Please show the report to your doctor.',
  hi: 'यह आपकी रिपोर्ट को आसान शब्दों में समझाता है। यह कोई निदान नहीं है। कृपया रिपोर्ट अपने डॉक्टर को दिखाएं।',
  kn: 'ಇದು ನಿಮ್ಮ ವರದಿಯನ್ನು ಸರಳ ಪದಗಳಲ್ಲಿ ವಿವರಿಸುತ್ತದೆ. ಇದು ರೋಗನಿರ್ಣಯವಲ್ಲ. ದಯವಿಟ್ಟು ವರದಿಯನ್ನು ನಿಮ್ಮ ವೈದ್ಯರಿಗೆ ತೋರಿಸಿ.',
} as const;

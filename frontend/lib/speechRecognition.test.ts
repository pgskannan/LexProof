import { describe, expect, it } from 'vitest';
import {
  getSpeechRecognitionConstructor,
  isSpeechRecognitionSupported,
  speechErrorMessage,
  transcriptFrom,
} from './speechRecognition';

class FakeRecognition {
  lang = '';
  continuous = false;
  interimResults = false;
  onresult = null;
  onerror = null;
  onend = null;
  start() {}
  stop() {}
  abort() {}
}

describe('getSpeechRecognitionConstructor', () => {
  it('returns null when neither constructor exists on the window', () => {
    expect(getSpeechRecognitionConstructor({})).toBeNull();
  });

  it('prefers the standard SpeechRecognition name when both exist', () => {
    const standard = FakeRecognition;
    const webkit = class extends FakeRecognition {};
    expect(getSpeechRecognitionConstructor({ SpeechRecognition: standard, webkitSpeechRecognition: webkit })).toBe(standard);
  });

  it('falls back to webkitSpeechRecognition when only that exists', () => {
    const webkit = FakeRecognition;
    expect(getSpeechRecognitionConstructor({ webkitSpeechRecognition: webkit })).toBe(webkit);
  });
});

describe('isSpeechRecognitionSupported', () => {
  it('is false with neither constructor present', () => {
    expect(isSpeechRecognitionSupported({})).toBe(false);
  });

  it('is true once a constructor is present', () => {
    expect(isSpeechRecognitionSupported({ SpeechRecognition: FakeRecognition })).toBe(true);
  });
});

describe('transcriptFrom', () => {
  it('concatenates every result transcript in order', () => {
    const event = {
      results: {
        length: 2,
        0: { 0: { transcript: 'what about ' } },
        1: { 0: { transcript: 'indemnification' } },
      },
    };
    expect(transcriptFrom(event)).toBe('what about indemnification');
  });

  it('returns an empty string for an empty result list', () => {
    expect(transcriptFrom({ results: { length: 0 } })).toBe('');
  });
});

describe('speechErrorMessage', () => {
  it('returns an empty string for a user-initiated abort', () => {
    expect(speechErrorMessage('aborted')).toBe('');
  });

  it('describes a denied-permission error', () => {
    expect(speechErrorMessage('not-allowed')).toMatch(/denied/i);
  });

  it('describes a no-speech-detected error', () => {
    expect(speechErrorMessage('no-speech')).toMatch(/no speech/i);
  });

  it('falls back to a generic message for an unrecognized code', () => {
    expect(speechErrorMessage('some-unknown-code')).toMatch(/voice input failed/i);
  });
});

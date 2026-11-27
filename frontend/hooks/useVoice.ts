"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* Browser-native voice: speech-to-text (Web Speech API) + text-to-speech (speechSynthesis). Free, no API key.
   Speech recognition works in Chrome/Edge (desktop + Android). It needs a secure page: localhost or https. */

interface RecognitionAlternative { transcript: string }
interface RecognitionResult { isFinal: boolean; 0: RecognitionAlternative; length: number }
interface RecognitionEvent { resultIndex: number; results: { length: number; [i: number]: RecognitionResult } }
interface Recognition {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start(): void; stop(): void; abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const MIC_ERRORS: Record<string, string> = {
  "not-allowed": "Microphone permission was blocked - allow it in the address bar.",
  "service-not-allowed": "Microphone needs a secure page (localhost or https).",
  "no-speech": "Didn't hear anything - try again.",
  "audio-capture": "No microphone found.",
  network: "Speech recognition needs an internet connection.",
};

/** Push-to-talk speech input. `onFinal` receives the recognised sentence. */
export function useSpeechInput(onFinal: (text: string) => void, lang = "en-IN") {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const finalCb = useRef(onFinal);
  useEffect(() => { finalCb.current = onFinal; }, [onFinal]);

  useEffect(() => { setSupported(!!recognitionCtor()); return () => rec.current?.abort(); }, []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    setError(null);
    setInterim("");
    const r = new Ctor();
    r.lang = lang; r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
    let finalText = "";
    r.onresult = (e) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) finalText += res[0].transcript; else live += res[0].transcript;
      }
      setInterim((finalText + " " + live).trim());
    };
    r.onerror = (e) => setError(MIC_ERRORS[e.error] ?? `Voice input error: ${e.error}`);
    r.onend = () => {
      setListening(false);
      setInterim("");
      if (finalText.trim()) finalCb.current(finalText.trim());
    };
    rec.current = r;
    try { r.start(); setListening(true); } catch { setListening(false); }
  }, [lang]);

  const stop = useCallback(() => rec.current?.stop(), []);
  return { supported, listening, interim, error, start, stop, toggle: listening ? stop : start };
}

/** Strip Markdown so the voice doesn't read symbols aloud. */
export function plainForSpeech(text: string) {
  return text
    .replace(/\[(\d+)\]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[*_`#>]/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/₹/g, "rupees ")
    .replace(/\n{2,}/g, ". ")
    .trim();
}

/** Text-to-speech with an Indian-English voice when the device has one. */
export function useSpeech(storageKey = "nb_auto_speak") {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [auto, setAutoState] = useState(false);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
    try { setAutoState(localStorage.getItem(storageKey) === "1"); } catch { /* storage unavailable */ }
    return () => { if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel(); };
  }, [storageKey]);

  const setAuto = useCallback((v: boolean) => {
    setAutoState(v);
    try { localStorage.setItem(storageKey, v ? "1" : "0"); } catch { /* storage unavailable */ }
    if (!v && typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
  }, [storageKey]);

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(plainForSpeech(text).slice(0, 1500));
    const voices = synth.getVoices();
    u.voice = voices.find((v) => v.lang === "en-IN") ?? voices.find((v) => v.lang.startsWith("en")) ?? null;
    u.lang = u.voice?.lang ?? "en-IN";
    u.rate = 1;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.speak(u);
  }, []);

  const stop = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  return { supported, speaking, auto, setAuto, speak, stop };
}

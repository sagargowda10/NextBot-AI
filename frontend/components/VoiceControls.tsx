"use client";

import { cx } from "@/components/ui";

/** Round mic button for push-to-talk. Hidden when the browser has no speech recognition. */
export function MicButton({ supported, listening, onClick, disabled }: { supported: boolean; listening: boolean; onClick: () => void; disabled?: boolean }) {
  if (!supported) return null;
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-pressed={listening}
            aria-label={listening ? "Stop listening" : "Speak your question"} title={listening ? "Stop listening" : "Speak your question"}
            className={cx("relative grid h-10 w-10 shrink-0 place-items-center rounded-full border transition disabled:opacity-50",
              listening ? "border-rose-500 bg-rose-500 text-white" : "border-ink-300 bg-white text-ink-700 hover:bg-ink-100")}>
      {listening && <span className="absolute inset-0 animate-ping rounded-full bg-rose-400/40" aria-hidden />}
      <svg viewBox="0 0 24 24" className="relative h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
      </svg>
    </button>
  );
}

/** "Read replies aloud" switch. */
export function SpeakToggle({ supported, auto, setAuto, speaking, stop }: { supported: boolean; auto: boolean; setAuto: (v: boolean) => void; speaking: boolean; stop: () => void }) {
  if (!supported) return null;
  return (
    <span className="flex items-center gap-2 text-xs text-ink-700">
      <label className="flex cursor-pointer items-center gap-1.5">
        <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> 🔊 Read replies aloud
      </label>
      {speaking && <button type="button" onClick={stop} className="rounded-full bg-ink-100 px-2 py-0.5 hover:bg-ink-300">Stop</button>}
    </span>
  );
}

/** Small per-message "listen" button. */
export function ListenButton({ supported, onClick }: { supported: boolean; onClick: () => void }) {
  if (!supported) return null;
  return <button type="button" onClick={onClick} className="text-xs text-ink-500 hover:text-brand-600" aria-label="Read this reply aloud">🔊 Listen</button>;
}

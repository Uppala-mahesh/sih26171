import { useState } from "react";

type TaskInputProps = {
  onStart: (url: string) => Promise<void>;
  onStop: () => Promise<void>;
  running: boolean;
};

export function TaskInput({ onStart, onStop, running }: TaskInputProps) {
  const [url, setUrl] = useState("https://example.com");
  const [busy, setBusy] = useState(false);

  const handleStart = async () => {
    setBusy(true);
    try {
      await onStart(url);
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    try {
      await onStop();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h2>Browser Control</h2>
      <input value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "70%" }} />
      <button disabled={busy || running} onClick={handleStart} style={{ marginLeft: 8 }}>
        Start
      </button>
      <button disabled={busy || !running} onClick={handleStop} style={{ marginLeft: 8 }}>
        Stop
      </button>
    </div>
  );
}

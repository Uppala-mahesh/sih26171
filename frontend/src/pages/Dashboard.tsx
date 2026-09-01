import { useEffect, useState } from "react";

import { BrowserViewer } from "../components/BrowserViewer";
import { TaskInput } from "../components/TaskInput";
import { checkHealth, getScreenshotUrl, startBrowser, stopBrowser } from "../services/api";

export function Dashboard() {
  const [health, setHealth] = useState("unknown");
  const [running, setRunning] = useState(false);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void checkHealth()
      .then((res) => setHealth(res.status))
      .catch(() => setHealth("down"));
  }, []);

  const handleStart = async (url: string) => {
    setError(null);
    await startBrowser(url);
    setRunning(true);
    await refreshScreenshot();
  };

  const handleStop = async () => {
    setError(null);
    await stopBrowser();
    setRunning(false);
    setScreenshotUrl(null);
  };

  const refreshScreenshot = async () => {
    setError(null);
    const next = await getScreenshotUrl();
    setScreenshotUrl((previous) => {
      if (previous) {
        URL.revokeObjectURL(previous);
      }
      return next;
    });
  };

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 1000, margin: "0 auto", padding: 16 }}>
      <h1>PS171 Milestone 1 Dashboard</h1>
      <p>Backend health: {health}</p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <TaskInput onStart={handleStart} onStop={handleStop} running={running} />
      <BrowserViewer screenshotUrl={screenshotUrl} onRefresh={refreshScreenshot} running={running} />
    </main>
  );
}

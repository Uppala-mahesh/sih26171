const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function checkHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error("Health check failed");
  }
  return response.json();
}

export async function startBrowser(url: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/browser/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    throw new Error("Failed to start browser");
  }
}

export async function stopBrowser(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/browser/stop`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to stop browser");
  }
}

export async function getScreenshotUrl(): Promise<string> {
  const response = await fetch(`${API_BASE}/api/browser/screenshot`);
  if (!response.ok) {
    throw new Error("Failed to capture screenshot");
  }

  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

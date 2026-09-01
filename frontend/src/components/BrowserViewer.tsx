type BrowserViewerProps = {
  screenshotUrl: string | null;
  onRefresh: () => Promise<void>;
  running: boolean;
};

export function BrowserViewer({ screenshotUrl, onRefresh, running }: BrowserViewerProps) {
  return (
    <div>
      <h2>Browser Screenshot</h2>
      <button disabled={!running} onClick={() => void onRefresh()}>
        Refresh Screenshot
      </button>
      <div style={{ marginTop: 12, border: "1px solid #ddd", minHeight: 300, display: "flex", alignItems: "center", justifyContent: "center" }}>
        {screenshotUrl ? (
          <img src={screenshotUrl} alt="Browser screenshot" style={{ maxWidth: "100%" }} />
        ) : (
          <p>No screenshot yet</p>
        )}
      </div>
    </div>
  );
}

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import './index.css'
import App from './App.tsx'

// The same UI is served both as a browser-action popup and as a standalone
// window. Only the window can be resized, so only it stretches to fill.
if (window.location.hash.startsWith('#detached')) {
  document.documentElement.classList.add('detached')
}

// Retokenize antd into the dossier look: ink on paper, square corners, one
// stamp color for anything that needs a human. Portaled surfaces (drawer,
// dropdown) read the same values, so every antd artifact agree with paper.
const ink = '#20242c'
const dim = '#6b6f79'
const paper = '#f6f1e4'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: ink,
          colorInfo: ink,
          colorLink: ink,
          colorSuccess: '#2e6b4f',
          colorWarning: '#8a6a1f',
          colorError: '#b3402a',
          colorText: ink,
          colorTextSecondary: dim,
          colorTextTertiary: '#9a968b',
          colorTextQuaternary: '#9a968b',
          colorBgContainer: paper,
          colorBgElevated: paper,
          colorBgLayout: '#e7dfcc',
          colorBorder: 'rgba(32, 36, 44, 0.5)',
          colorBorderSecondary: 'rgba(32, 36, 44, 0.24)',
          borderRadius: 2,
          controlHeight: 28,
          fontFamily:
            "'Anek Devanagari Variable', ui-sans-serif, system-ui, sans-serif",
        },
      }}
    >
      <App />
    </ConfigProvider>
  </StrictMode>,
)

import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Divider,
  Drawer,
  Input,
  Typography,
  message,
} from 'antd'
import {
  ApiOutlined,
  CheckCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import type { UserSettings } from '../../shared/types/drishti'
import { DEFAULT_SETTINGS, loadSettings, saveSettings } from '../../shared/lib/settingsStorage'
import './SettingsDrawer.css'

type SettingsDrawerProps = {
  open: boolean
  onClose: () => void
  onSettingsChanged?: (settings: UserSettings) => void
}

type HealthSnapshot = {
  browserConnected: boolean
  modelChain: string[]
  activeTask: string | null
}

function agentSocketUrl(healthUrl: string): string | null {
  try {
    const parsed = new URL(healthUrl)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    const socket = new URL('/ws/agent', parsed)
    socket.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
    return socket.toString()
  } catch {
    return null
  }
}

async function rememberAgentServer(healthUrl: string): Promise<boolean> {
  if (typeof chrome === 'undefined' || !chrome.storage?.local) return false
  const socketUrl = agentSocketUrl(healthUrl)
  if (!socketUrl) return false
  await new Promise<void>((resolve) => {
    chrome.storage.local.set({ agentServerUrl: socketUrl }, () => resolve())
  })
  try {
    chrome.runtime?.sendMessage?.({ type: 'AGENT_RECONNECT' })
  } catch {
    // The server URL is still stored; the next service-worker boot reconnects.
  }
  return true
}

export function SettingsDrawer({ open, onClose, onSettingsChanged }: SettingsDrawerProps) {
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS)
  const [testingServer, setTestingServer] = useState(false)
  const [serverStatus, setServerStatus] = useState<'idle' | 'online' | 'offline'>('idle')
  const [health, setHealth] = useState<HealthSnapshot | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      loadSettings().then((loaded) => {
        setSettings(loaded)
        setServerStatus('idle')
        setHealth(null)
      })
    }
  }, [open])

  async function handleSave() {
    setSaving(true)
    try {
      const updated = await saveSettings(settings)
      const rewired = await rememberAgentServer(updated.serverUrl)
      onSettingsChanged?.(updated)
      message.success(rewired
        ? 'Saved. The extension is reconnecting to this server.'
        : 'Settings saved successfully')
    } catch {
      message.error('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  async function testServerConnection() {
    setTestingServer(true)
    setServerStatus('idle')
    setHealth(null)
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    try {
      const controller = new AbortController()
      timeoutId = setTimeout(() => controller.abort(), 3000)
      const res = await fetch(settings.serverUrl, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      })
      if (!res.ok) {
        setServerStatus('offline')
        message.warning(`Server responded with status ${res.status}`)
        return
      }
      const data = await res.json().catch(() => null) as Record<string, unknown> | null
      setServerStatus('online')
      setHealth({
        browserConnected: Boolean(data?.browser_connected),
        modelChain: Array.isArray(data?.model_chain)
          ? (data.model_chain as unknown[]).map(String)
          : [],
        activeTask: typeof data?.active_task === 'string' ? data.active_task : null,
      })
      message.success('Drishti server is reachable')
    } catch {
      setServerStatus('offline')
      message.error('Drishti server is unreachable. Start it with npm run server.')
    } finally {
      if (timeoutId) clearTimeout(timeoutId)
      setTestingServer(false)
    }
  }

  return (
    <Drawer
      className="settings-drawer"
      closeIcon={<span className="settings-close">✕</span>}
      onClose={onClose}
      open={open}
      placement="right"
      title={
        <div className="settings-drawer-header">
          <SafetyCertificateOutlined className="header-icon" />
          <div>
            <div className="title-text">Drishti Settings</div>
            <div className="subtitle-text">Local server & on-device stack</div>
          </div>
        </div>
      }
      width={360}
    >
      <div className="settings-content">
        <section className="settings-section">
          <Typography.Text className="section-label">Local Drishti Server</Typography.Text>
          <Typography.Paragraph className="section-hint">
            The extension sends only sanitized context to this server on your own machine.
            Checking the health URL below also confirms the server is running.
          </Typography.Paragraph>

          <div className="server-input-group">
            <Input
              onChange={(e) => {
                const updated = { ...settings, serverUrl: e.target.value }
                setSettings(updated)
                setServerStatus('idle')
                setHealth(null)
              }}
              placeholder="http://127.0.0.1:8787/health"
              prefix={<ApiOutlined style={{ color: 'var(--ink-faint)' }} />}
              value={settings.serverUrl}
            />
            <Button loading={testingServer} onClick={testServerConnection} type="default">
              Test
            </Button>
          </div>

          {serverStatus === 'online' && (
            <Alert
              className="server-alert"
              icon={<CheckCircleOutlined />}
              message="Drishti server is online"
              description={health ? (
                <span>
                  Browser: {health.browserConnected ? 'connected' : 'not connected'}
                  {health.modelChain.length > 0 ? ` · models: ${health.modelChain.join(' > ')}` : ''}
                  {health.activeTask ? ' · task running' : ''}
                </span>
              ) : undefined}
              showIcon
              type="success"
            />
          )}
          {serverStatus === 'offline' && (
            <Alert
              className="server-alert"
              message="Server unreachable at this address"
              description="Start it with: npm run server — then load the extension from dist/."
              showIcon
              type="error"
            />
          )}
        </section>

        <Divider className="settings-divider" />

        <section className="settings-section">
          <Typography.Text className="section-label">What runs on this device</Typography.Text>
          <div className="specs-card">
            <div className="spec-row">
              <span className="spec-key">Screen OCR</span>
              <span className="spec-val">Tesseract · bundled · offline</span>
            </div>
            <div className="spec-row">
              <span className="spec-key">Visual grounding</span>
              <span className="spec-val">MobileCLIP-S0 · bundled · offline</span>
            </div>
            <div className="spec-row">
              <span className="spec-key">PII masking</span>
              <span className="spec-val">Deterministic DOM sanitizer · in-page</span>
            </div>
            <div className="spec-row">
              <span className="spec-key">Reasoning</span>
              <span className="spec-val">Cloud model · sanitized context only</span>
            </div>
          </div>
        </section>

        <Divider className="settings-divider" />

        <section className="settings-section">
          <Typography.Text className="section-label">Privacy boundary</Typography.Text>
          <Typography.Paragraph className="section-hint">
            Page text and field values are masked in the browser before serialization.
            The raw screenshot never leaves the browser; the masked screenshot is withheld
            entirely if the on-device re-OCR finds residual personal data.
          </Typography.Paragraph>
        </section>

        <div className="settings-actions">
          <Button block loading={saving} onClick={handleSave} type="primary">
            Save Changes
          </Button>
        </div>
      </div>
    </Drawer>
  )
}

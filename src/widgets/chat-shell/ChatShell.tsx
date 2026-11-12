import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import {
  ArrowUpOutlined,
  AudioMutedOutlined,
  AudioOutlined,
  CloseOutlined,
  LockOutlined,
  PlusOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Button, Input, Select, Tooltip, Typography } from 'antd'
import type {
  AgentEffort,
  AgentMode,
  ChatHistoryThread,
  ChatMessage,
  MaskingReport,
  PendingConfirmation,
} from '../../features/agent-runner/model'
import { EFFORT_LABELS } from '../../features/agent-runner/model'
import { privacyModes } from '../../entities/mode/model'
import type { PrivacyMode } from '../../shared/types/drishti'
import { openMicrophonePermissionTab, useSpeechToText } from '../../shared/lib/useSpeechToText'
import { SettingsDrawer } from '../settings/SettingsDrawer'
import './ChatShell.css'

/* Renders operator-facing text with every [REDACTED:*] token as a censor
   bar: true black ink with a tiny mono label. What the model never saw, the
   operator sees redacted too -- the report stream and its own summary agree. */
const REDACTED_TOKEN = /\[REDACTED:[A-Za-z0-9_]+\]/g

type BrowserTab = { id?: number; url?: string; title?: string }
type TabsApi = {
  query: (
    info: { active: boolean; currentWindow: boolean },
    callback: (tabs: BrowserTab[]) => void,
  ) => void
  sendMessage: (
    tabId: number,
    message: { type: string },
    callback: (reply?: { text?: string }) => void,
  ) => void
}

function tabsApi(): TabsApi | null {
  if (typeof chrome === 'undefined') return null
  return (chrome as unknown as { tabs?: TabsApi }).tabs ?? null
}

export function DocketText({ value }: { value: string | undefined | null }) {
  if (!value) return null
  return (
    <>
      {value.split(REDACTED_TOKEN).map((part, i) => {
        const bare = part.match(/^\[REDACTED:([A-Za-z0-9_]+)\]$/)
        if (bare) {
          return (
            <span className="censor-bar" data-kind={bare[1]} key={i}>
              {part}
            </span>
          )
        }
        return part
      })}
    </>
  )
}

type ChatShellProps = {
  extensionReady: boolean
  isRunning: boolean
  messages: ChatMessage[]
  mode: PrivacyMode
  effort: AgentEffort
  agentMode: AgentMode
  error?: string
  statusText: string
  task: string
  maskedScreenshot?: string | null
  maskedCount?: number
  pageLine?: string
  hasPage?: boolean
  masking?: MaskingReport | null
  blocked?: string[]
  history?: ChatHistoryThread[]
  pending?: PendingConfirmation | null
  preApprove?: boolean
  onPreApproveChange?: (value: boolean) => void
  onApprove?: () => void
  onApproveAll?: () => void
  onDeny?: () => void
  onCancel?: () => void
  onNewChat?: () => void
  onDetach?: () => void
  isDetached?: boolean
  onModeChange: (mode: PrivacyMode) => void
  onEffortChange: (effort: AgentEffort) => void
  onAgentModeChange: (mode: AgentMode) => void
  onDismissError?: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onTaskChange: (task: string) => void
  localModelStatus?: string | null
}

export function ChatShell({
  extensionReady,
  isRunning,
  messages,
  mode,
  effort,
  agentMode,
  error,
  statusText,
  task,
  maskedScreenshot,
  maskedCount = 0,
  pageLine = '',
  hasPage = true,
  masking,
  blocked = [],
  history = [],
  pending,
  preApprove = false,
  onPreApproveChange,
  onApprove,
  onApproveAll,
  onDeny,
  onCancel,
  onNewChat,
  onDetach,
  isDetached = false,
  onModeChange,
  onEffortChange,
  onAgentModeChange,
  onDismissError,
  onSubmit,
  onTaskChange,
  localModelStatus,
}: ChatShellProps) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [shieldOpen, setShieldOpen] = useState(false)
  const [activePanel, setActivePanel] = useState<'chat' | 'details' | 'history'>('chat')
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [contextOpen, setContextOpen] = useState(false)
  const [contextNote, setContextNote] = useState('')
  const contextRef = useRef<HTMLDivElement | null>(null)

  // ---- Speech-to-Text ---------------------------------------------------
  // The hook handles Hindi, Hinglish, and English in a single pass.
  // Interim results appear in the composer live; on final the transcript
  // is appended to whatever the user had already typed.
  const stt = useSpeechToText({
    onInterim: () => {
      // Interim is shown via stt.interimText — no state change needed here.
    },
    onFinal: (text) => {
      // Append final transcript to existing task (with a space separator).
      onTaskChange(
        (task.trim() ? task.trim() + ' ' : '') + text
      )
    },
    onError: (msg) => {
      setVoiceError(msg)
      setTimeout(() => setVoiceError(null), 6000)
    },
  })

  /**
   * Keep the newest line in view, the way every chat does.
   *
   * The thread scrolls, but nothing was ever scrolling it, so each new line
   * landed below the fold: you sent something and the view stayed where it
   * was, showing older text, as though your message had gone nowhere.
   *
   * Following is conditional on already being at the bottom. If you have
   * scrolled up to read something, arriving text must not yank you away --
   * a chat that fights you when you scroll back is worse than one that
   * does not follow at all.
   */
  const threadRef = useRef<HTMLElement | null>(null)
  const stickToBottom = useRef(true)

  const onThreadScroll = () => {
    const node = threadRef.current
    if (!node) return
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight
    stickToBottom.current = distanceFromBottom < 60
  }

  useEffect(() => {
    const node = threadRef.current
    if (!node || !stickToBottom.current) return
    node.scrollTop = node.scrollHeight
  }, [messages, statusText, pending, isRunning])

  // Whatever you type is the newest thing in the thread by definition, so
  // sending always returns you to the bottom even if you had scrolled up.
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    stickToBottom.current = true
    onSubmit(event)
  }

  const modeOptions = privacyModes.map((privacyMode) => ({
    label: privacyMode.title,
    value: privacyMode.id,
  }))
  const hasDetails = Boolean(masking || blocked.length > 0 || maskedScreenshot)
  const historyCount = history.length

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) {
      return
    }

    event.preventDefault()

    if (isRunning || !task.trim()) {
      return
    }

    event.currentTarget.form?.requestSubmit()
  }

  // ---- context tray -------------------------------------------------------
  // The "+" used to be decoration. These four actions put something real into
  // the composer, and every one of them is inspectable before it is sent.
  const appendContext = (raw: string) => {
    const text = raw.trim()
    if (!text) return
    const base = task.trim()
    onTaskChange(base ? `${base} ${text}` : text)
    setContextOpen(false)
    setContextNote('')
  }

  const flashContext = (note: string) => {
    setContextNote(note)
    window.setTimeout(() => setContextNote(''), 3500)
  }

  const addCurrentPage = () => {
    const tabs = tabsApi()
    if (!tabs) {
      flashContext('Page context is available inside the extension.')
      return
    }
    try {
      tabs.query({ active: true, currentWindow: true }, (found) => {
        if (chrome.runtime?.lastError) {
          flashContext('Could not read the active tab.')
          return
        }
        const tab = found?.[0]
        if (!tab?.url || !/^https?:/i.test(tab.url)) {
          flashContext('Open a normal http(s) page first.')
          return
        }
        appendContext(`On this page (${tab.title || 'untitled page'} — ${tab.url}): `)
      })
    } catch {
      flashContext('Page context is available inside the extension.')
    }
  }

  const addSelection = () => {
    const tabs = tabsApi()
    if (!tabs) {
      flashContext('Selection is available inside the extension.')
      return
    }
    try {
      tabs.query({ active: true, currentWindow: true }, (found) => {
        const tabId = found?.[0]?.id
        if (tabId === undefined) {
          flashContext('No active page to read a selection from.')
          return
        }
        tabs.sendMessage(tabId, { type: 'AGENT_SELECTION' }, (reply) => {
          if (chrome.runtime?.lastError) {
            flashContext('Reload the page, then try again.')
            return
          }
          const text = typeof reply?.text === 'string' ? reply.text.trim() : ''
          if (!text) {
            flashContext('Select some text on the page first.')
            return
          }
          appendContext(`Selected text from the page: "${text.slice(0, 1500)}"`)
        })
      })
    } catch {
      flashContext('Selection is available inside the extension.')
    }
  }

  const pasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) {
        flashContext('Clipboard is empty.')
        return
      }
      appendContext(text.slice(0, 2000))
    } catch {
      flashContext('Clipboard permission was not granted.')
    }
  }

  useEffect(() => {
    if (!contextOpen) return
    const onDown = (event: MouseEvent) => {
      if (contextRef.current && !contextRef.current.contains(event.target as Node)) {
        setContextOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [contextOpen])

  return (
    <main className="chat-popup" aria-label="Drishti assistant">
      <section className="assistant-header" aria-label="Assistant status">
        <div className="brand-lockup">
          <div className="brand-orb" aria-hidden="true">
            <img src="./icons/icon-128.png" alt="" />
          </div>
          <div>
            <Typography.Text className="brand-title">
              Drishti
              <span
                className={`brand-status-dot${isRunning ? ' busy' : extensionReady ? ' ready' : ''}`}
                aria-hidden="true"
              />
            </Typography.Text>
            <Typography.Text className="brand-subtitle">
              {isRunning
                ? statusText || 'Working…'
                : agentMode === 'ask'
                  ? 'Read-only page assistant'
                  : 'Private page assistant'}
            </Typography.Text>
            {localModelStatus && (
              <span className="nano-pill">Nano: {localModelStatus}</span>
            )}
          </div>
        </div>
        {!isDetached && (
          <Button
            className="detach-button"
            size="small"
            type="text"
            onClick={onDetach}
            title="Chrome closes this popup whenever the agent opens a tab. Open it as its own window and it stays put."
          >
            Keep open
          </Button>
        )}
      </section>

      <div className="agent-mode-bar">
        <div className="agent-mode-switch" role="tablist" aria-label="Interaction mode">
          <button
            type="button"
            role="tab"
            aria-selected={agentMode === 'agent'}
            className={agentMode === 'agent' ? 'active' : ''}
            onClick={() => onAgentModeChange('agent')}
            title="Drishti can click, type and navigate, with policy checks and approval."
          >
            Agent
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={agentMode === 'ask'}
            className={agentMode === 'ask' ? 'active' : ''}
            onClick={() => onAgentModeChange('ask')}
            title="Read-only conversation about the page. Nothing is clicked or typed."
          >
            Ask
          </button>
        </div>
        <div className="effort-switch" role="group" aria-label="Reasoning effort">
          <span className="effort-label">Power</span>
          {(['fast', 'balanced', 'deep'] as AgentEffort[]).map((level) => (
            <button
              type="button"
              key={level}
              aria-pressed={effort === level}
              className={effort === level ? 'active' : ''}
              onClick={() => onEffortChange(level)}
              title={
                level === 'fast'
                  ? 'Short run, no vision calls. Cheapest and quickest.'
                  : level === 'deep'
                    ? 'Longer run and more visual checks. Slowest, most thorough.'
                    : 'Balanced loop with periodic redacted screenshots.'
              }
            >
              {EFFORT_LABELS[level]}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button type="button" aria-label="Dismiss error" onClick={onDismissError}>
            <CloseOutlined />
          </button>
        </div>
      )}

      <SettingsDrawer
        onClose={() => setSettingsOpen(false)}
        open={settingsOpen}
      />

      <nav className="panel-tabs" aria-label="Drishti views">
        <button
          type="button"
          className={activePanel === 'chat' ? 'active' : ''}
          onClick={() => setActivePanel('chat')}
        >
          Chat
        </button>
        <button
          type="button"
          className={activePanel === 'details' ? 'active' : ''}
          onClick={() => setActivePanel('details')}
        >
          More details
          {hasDetails && <span className="details-dot" aria-hidden="true" />}
        </button>
        <button
          type="button"
          className={activePanel === 'history' ? 'active' : ''}
          onClick={() => setActivePanel('history')}
        >
          History
          {historyCount > 0 && <span className="tab-count">{historyCount}</span>}
        </button>
        <button
          type="button"
          className="new-chat-tab"
          disabled={isRunning}
          onClick={() => {
            onNewChat?.()
            setActivePanel('chat')
          }}
        >
          New chat
        </button>
      </nav>

      {activePanel === 'chat' && messages.length === 0 && !isRunning && (
        <section className="hero-copy" aria-label="Greeting">
          <Typography.Title level={1}>
            <span>{agentMode === 'ask' ? 'Question, filed.' : 'Case file, opened.'}</span>
            {agentMode === 'ask' ? 'What should Drishti read?' : 'What should Drishti do?'}
          </Typography.Title>
          <Typography.Paragraph>
            {agentMode === 'ask'
              ? 'Ask about the page in plain words. Drishti reads and scrolls, but never clicks, types or submits in Ask mode.'
              : 'Command the agent in plain words. Every line it reads is screened on this machine before it reaches any model.'}
          </Typography.Paragraph>

          <div className="quick-actions-list">
            <button
              type="button"
              className="quick-action-pill"
              onClick={() => onTaskChange(
                agentMode === 'ask'
                  ? 'Summarize this page in plain language, with the most important facts first'
                  : 'Scroll through the whole page and give a complete summary',
              )}
            >
              <span className="qa-icon" aria-hidden="true">§</span>
              <span className="qa-text">
                {agentMode === 'ask' ? 'Summarize This Page' : 'Full Page Scroll & Summarize'}
              </span>
            </button>
            <button
              type="button"
              className="quick-action-pill"
              onClick={() => onTaskChange(
                agentMode === 'ask'
                  ? 'What needs my attention on this page? List the important items and quote the evidence for each.'
                  : 'Scan and redact all sensitive PII on this page',
              )}
            >
              <span className="qa-icon" aria-hidden="true">{agentMode === 'ask' ? '!' : '⊘'}</span>
              <span className="qa-text">
                {agentMode === 'ask' ? 'What Needs Attention?' : 'Scan & Redact Sensitive PII'}
              </span>
            </button>
            <button
              type="button"
              className="quick-action-pill"
              onClick={() => onTaskChange(
                agentMode === 'ask'
                  ? 'Find the key dates, amounts and deadlines on this page, with the exact text that states each one.'
                  : 'Open the main form on this page and fill it from the context I provide',
              )}
            >
              <span className="qa-icon" aria-hidden="true">{agentMode === 'ask' ? '⌕' : '▤'}</span>
              <span className="qa-text">
                {agentMode === 'ask' ? 'Find Dates & Amounts' : 'Work Through a Form'}
              </span>
            </button>
          </div>
        </section>
      )}

      {activePanel === 'chat' && (messages.length > 0 || isRunning) && (
        <section
          className="chat-thread"
          aria-label="Conversation"
          ref={threadRef}
          onScroll={onThreadScroll}
        >
          {messages.map((message) => (
            <div className={`message-row ${message.role}`} key={message.id}>
              {message.role === 'assistant' && (
                <span className="message-avatar" aria-hidden="true">N</span>
              )}
              <article className={`message ${message.role}`}>
                <DocketText value={message.text} />
              </article>
            </div>
          ))}
          {isRunning && (
            <div className="message-row assistant">
              <span className="message-avatar" aria-hidden="true">N</span>
              <article className="message assistant pending">{statusText}</article>
            </div>
          )}
          {pending && (
            <div className="approval-card" role="alertdialog" aria-label="Approval required">
              <div className="approval-head">
                <span className="approval-dot" />
                <span>Approval needed</span>
                {pending.requiresLiveHuman && (
                  <span className="approval-live">cannot be pre-approved</span>
                )}
              </div>
              <div className="approval-action"><DocketText value={pending.preview} /></div>
              {pending.textPreview && (
                <div className="approval-text"><DocketText value={pending.textPreview} /></div>
              )}
              <dl className="approval-meta">
                <dt>page</dt><dd>{pending.url}</dd>
                {pending.reason ? (<><dt>why</dt><dd><DocketText value={pending.reason} /></dd></>) : null}
                <dt>rules</dt><dd>{pending.rulesFired.join(', ') || '—'}</dd>
              </dl>
              {pending.screenshot && (
                <img
                  src={pending.screenshot}
                  alt="Page at the moment of the request, sensitive regions blacked out"
                  className="approval-img"
                />
              )}
              <div className="approval-actions">
                <Button size="small" onClick={onDeny}>Cancel</Button>
                {!pending.requiresLiveHuman && (
                  <Button size="small" onClick={onApproveAll}>Don't ask again</Button>
                )}
                <Button size="small" type="primary" onClick={onApprove}>Approve</Button>
              </div>
            </div>
          )}
        </section>
      )}

      {activePanel === 'details' && (
        <section className="details-panel" aria-label="More details">
          {!hasDetails && (
            <div className="details-empty">
              Redaction details will appear here after Drishti reads a page.
            </div>
          )}

          {(masking || blocked.length > 0) && (
            <section className="shield-panel" aria-label="What was hidden from the model">
              <button
                type="button"
                className="shield-head"
                onClick={() => setShieldOpen((open) => !open)}
                aria-expanded={shieldOpen}
              >
                <span className="shield-dot" />
                <span className="shield-title">
                  {masking ? `${masking.piiTotal + masking.maskedRegions} hidden before the model read anything` : 'Blocked'}
                </span>
                <span className="shield-caret">{shieldOpen ? '−' : '+'}</span>
              </button>

              {masking && (
                <div className="shield-chips">
                  {Object.entries(masking.byType).map(([kind, n]) => (
                    <span className="shield-chip" key={kind}>{kind} ×{n}</span>
                  ))}
                  {masking.occurrences > masking.piiTotal && (
                    <span className="shield-chip quiet">
                      in {masking.occurrences} places
                    </span>
                  )}
                  {masking.maskedRegions > 0 && (
                    <span className="shield-chip regions">blacked out ×{masking.maskedRegions}</span>
                  )}
                  {masking.injectionsNeutralized > 0 && (
                    <span className="shield-chip danger">
                      page tried to give orders ×{masking.injectionsNeutralized}
                    </span>
                  )}
                  {masking.readBySight && (
                    <span className="shield-chip danger">read from a screenshot</span>
                  )}
                  {masking.piiTotal === 0 && masking.maskedRegions === 0 && !masking.readBySight && (
                    <span className="shield-chip quiet">nothing sensitive on this page</span>
                  )}
                </div>
              )}

              {masking?.maskNote && (
                <p className="shield-warn">{masking.maskNote}</p>
              )}

              {shieldOpen && masking && (
                <>
                  <p className="shield-note">
                    This is the text the model actually received. Every
                    <code>[REDACTED:…]</code> is a value it never saw.
                  </p>
                  <pre className="shield-sample">{masking.llmInputSample || '(no page text)'}</pre>
                  {masking.regions.length > 0 && (
                    <>
                      <p className="shield-note">
                        Each black box on the snapshot, and what it covers.
                      </p>
                      <ul className="shield-injections">
                        {masking.regions.map((r, i) => (
                          <li key={i}>
                            <b>{r.kind}</b> — {r.box[2]}×{r.box[3]} at {r.box[0]},{r.box[1]}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {masking.injections.length > 0 && (
                    <ul className="shield-injections">
                      {masking.injections.map((item, i) => (
                        <li key={i}><b>{item.kind}</b> — {item.text}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}

              {blocked.map((reason, i) => (
                <p className="shield-blocked" key={i}>{reason}</p>
              ))}
            </section>
          )}

          {maskedScreenshot && (
            <section className="masked-proof-dock" aria-label="Masked snapshot proof">
              <div className="masked-proof-card" role="region" aria-label="Masked Snapshot Proof">
                <div className="masked-proof-header">
                  <div className="masked-proof-badge">
                    <span className="masked-proof-dot" />
                    <span>🛡️ On-Device Redaction</span>
                  </div>
                  <span className="masked-proof-count">{maskedCount} PII Masked</span>
                </div>
                <div className="masked-proof-img-wrap">
                  <img src={maskedScreenshot} alt="Visual Redaction Proof" className="masked-proof-img" />
                  <div className="masked-proof-tag">Visual Masking Proof</div>
                </div>
              </div>
            </section>
          )}
        </section>
      )}

      {activePanel === 'history' && (
        <section className="history-panel" aria-label="Chat history">
          {history.length === 0 ? (
            <div className="details-empty">
              Previous chats will appear here when you open a new page or start a new chat.
            </div>
          ) : (
            history.map((thread) => (
              <article className="history-thread" key={thread.id}>
                <header className="history-head">
                  <div>
                    <h2>{thread.title}</h2>
                    {thread.pageUrl && <p>{thread.pageUrl}</p>}
                  </div>
                  <time dateTime={thread.createdAt}>
                    {new Date(thread.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </time>
                </header>
                <div className="history-messages">
                  {thread.messages.slice(-6).map((message) => (
                    <p className={`history-message ${message.role}`} key={message.id}>
                      {message.text}
                    </p>
                  ))}
                </div>
              </article>
            ))
          )}
        </section>
      )}

      {activePanel === 'chat' && pageLine && (
        <p className={`page-line${hasPage ? '' : ' none'}`}>{pageLine}</p>
      )}

      {activePanel === 'chat' && <form className="composer" onSubmit={handleSubmit}>
        {/* Live voice indicator shown above composer when mic is active */}
        {stt.status === 'listening' && (
          <div className="voice-indicator" aria-live="polite" aria-label="Listening for voice command">
            <span className="voice-dot" />
            <span className="voice-label">Listening…</span>
            {stt.interimText && (
              <span className="voice-interim">{stt.interimText}</span>
            )}
          </div>
        )}

        {/* Error toast from mic (denied, no-speech, etc.) */}
        {voiceError && (
          <div
            className="voice-error"
            role="alert"
            onClick={openMicrophonePermissionTab}
            title="Click to open microphone setup page"
            style={{ cursor: 'pointer' }}
          >
            {voiceError}
          </div>
        )}

        <Input.TextArea
          aria-label={agentMode === 'ask' ? 'Ask about this page' : 'Ask Drishti'}
          autoSize={{ minRows: 3, maxRows: 10 }}
          className={`composer-input${stt.status === 'listening' ? ' composer-input--listening' : ''}`}
          // A real task command carries a URL or two, the columns wanted and
          // the shape of the answer, and goes well past 240 characters. The old
          // cap did not warn or wrap -- it silently dropped the tail, so a
          // pasted command arrived at the planner cut off mid-word and the
          // agent worked, correctly and confidently, from half an instruction.
          maxLength={4000}
          onChange={(event) => onTaskChange(event.target.value)}
          onKeyDown={handleComposerKeyDown}
          placeholder={
            stt.status === 'listening'
              ? 'Bol do… Hindi, Hinglish ya English mein'
              : agentMode === 'ask'
                ? 'Ask about this page — Drishti reads, never acts…'
                : 'Ask Drishti to inspect, explain, or act...'
          }
          value={stt.status === 'listening' && stt.interimText
            ? (task.trim() ? task.trim() + ' ' : '') + stt.interimText
            : task
          }
        />
        <div className="composer-actions">
          <div className="composer-tools">
            <div className="context-wrap" ref={contextRef}>
              <Button
                className={`context-button${contextOpen ? ' open' : ''}`}
                icon={<PlusOutlined />}
                shape="circle"
                type="text"
                aria-label="Add context"
                aria-haspopup="menu"
                aria-expanded={contextOpen}
                onClick={() => setContextOpen((open) => !open)}
              />
              {contextOpen && (
                <div className="context-popover" role="menu" aria-label="Add context">
                  <div className="context-popover-head">Add context</div>
                  <button type="button" role="menuitem" onClick={addCurrentPage}>
                    <b>Current page</b>
                    <span>title and URL</span>
                  </button>
                  <button type="button" role="menuitem" onClick={addSelection}>
                    <b>Selected text</b>
                    <span>the part you highlighted</span>
                  </button>
                  <button type="button" role="menuitem" onClick={pasteClipboard}>
                    <b>Clipboard</b>
                    <span>paste text to work from</span>
                  </button>
                  <button type="button" role="menuitem" onClick={() => { onTaskChange(''); setContextOpen(false) }}>
                    <b>Clear composer</b>
                    <span>start this question fresh</span>
                  </button>
                  {contextNote && <p className="context-note" role="status">{contextNote}</p>}
                </div>
              )}
            </div>
            {/* ---- Microphone button ---- */}
            <Tooltip
              title={
                !stt.isSupported
                  ? 'Voice input not supported in this browser'
                  : stt.status === 'listening'
                  ? 'Click to stop listening'
                  : 'Voice input — Hindi, Hinglish or English'
              }
            >
              <Button
                id="voice-input-btn"
                aria-label={stt.status === 'listening' ? 'Stop voice input' : 'Start voice input'}
                aria-pressed={stt.status === 'listening'}
                className={`mic-button${
                  !stt.isSupported ? ' mic-button--unsupported' : ''
                }${
                  stt.status === 'listening' ? ' mic-button--listening' : ''
                }`}
                disabled={!stt.isSupported || isRunning}
                icon={
                  !stt.isSupported
                    ? <AudioMutedOutlined />
                    : <AudioOutlined />
                }
                onClick={stt.toggle}
                shape="circle"
                type="text"
              />
            </Tooltip>

            <Button
              aria-label="Open Settings"
              className="settings-button"
              icon={<SettingOutlined />}
              onClick={() => setSettingsOpen(true)}
              shape="circle"
              type="text"
            />
          </div>
          <div className="privacy-control">
            <span className="privacy-mark" title="Privacy mode: how aggressively page text is masked before it leaves the browser">
              <LockOutlined />
            </span>
            <Select
              aria-label="Privacy mode"
              className="mode-select"
              onChange={onModeChange}
              options={modeOptions}
              popupClassName="mode-dropdown"
              title="How aggressively page text is masked before it leaves the browser"
              value={mode}
              variant="borderless"
            />
          </div>
          {isRunning ? (
            <Button className="stop-button" size="small" danger onClick={onCancel} aria-label="Stop the task">
              Stop
            </Button>
          ) : (
            <Button
              className="send-button"
              disabled={!task.trim()}
              htmlType="submit"
              icon={<ArrowUpOutlined />}
              shape="circle"
              type="primary"
              aria-label={agentMode === 'ask' ? 'Ask' : 'Send'}
            />
          )}
        </div>
      </form>}

      {activePanel === 'chat' && agentMode === 'agent' && <label className="preapprove-row" title="Remembered across tasks. High-risk actions stay classified and logged either way — this only changes whether you answer up front or one at a time. Authentication codes always need you, live.">
        <input
          type="checkbox"
          checked={preApprove}
          onChange={(event) => onPreApproveChange?.(event.target.checked)}
        />
        <span>Don't ask before sending, posting or paying</span>
      </label>}

      {!extensionReady && <p className="dev-note">Load the built dist folder as an unpacked Chrome extension.</p>}
    </main>
  )
}

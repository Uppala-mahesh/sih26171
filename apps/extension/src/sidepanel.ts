/**
 * SIH26171 — Side panel: the operator's view of the last observation.
 *
 * ── What this may show ────────────────────────────────────────────────────────
 * Verdicts, states, counts and reasons. **Never a value.** The panel is an
 * extension page, which means it is a surface a page can influence indirectly and
 * a place a user will screenshot into a bug report. Showing the redacted text
 * here would put placeholders on screen next to a UI an attacker may be
 * screenshotting, and the placeholder set is the half of the B-6 pair that a
 * detokenization request needs.
 *
 * The rule is: counts and verdicts only, and every string arrives as a TEXT NODE.
 * A verdict is data like any other, and `textContent` is what makes "this came
 * from our own code" true rather than merely likely.
 *
 * ── Why it re-runs rather than only reading ───────────────────────────────────
 * Reading a stored report would leave the operator unable to tell a stale verdict
 * from a current one. The panel therefore offers a Run button and shows the
 * observation's age, because a verdict without a timestamp is not evidence.
 */

import { isPanelMessage, type ReportView } from './messages.js';

const STALE_AFTER_MS = 5 * 60 * 1000;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  // textContent, never innerHTML: see the header.
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

const STATE_COPY: Record<string, { title: string; detail: string }> = {
  SANITIZED: {
    title: 'Sanitized',
    detail: 'Every text segment was scanned and sensitive values were replaced.',
  },
  DEGRADED: {
    title: 'Degraded',
    detail:
      'Text was fully sanitised and sent, but painted content could not be ' +
      'inspected. That limitation travels with the payload.',
  },
  UNCERTAIN: {
    title: 'Uncertain',
    detail:
      'Some entity types fell below the confidence threshold and were redacted ' +
      'anyway. The types are listed below.',
  },
  NOT_INSTRUMENTED: {
    title: 'Withheld',
    detail: 'Nothing was sent: a required check could not run.',
  },
};

function row(label: string, value: string): HTMLElement {
  const wrapper = el('div', '');
  wrapper.className = 'row';
  wrapper.append(el('span', label, 'label'), el('span', value, 'value'));
  return wrapper;
}

function render(report: ReportView): void {
  const root = document.getElementById('report');
  if (!root) return;
  root.textContent = '';

  const copy = STATE_COPY[report.state] ?? {
    title: report.state,
    detail: 'Unrecognised state. Treat this as withheld.',
  };

  const header = el('div', '');
  header.className = `verdict ${report.state.toLowerCase()}`;
  header.append(
    el('h1', copy.title),
    el('p', copy.detail, 'detail'),
  );
  root.append(header);

  const age = Math.max(0, Date.now() - report.capturedAt);
  const ageText =
    age > STALE_AFTER_MS
      ? `STALE — ${Math.round(age / 1000)}s old`
      : `${Math.round(age / 1000)}s ago`;

  const facts = el('div', '');
  facts.className = 'facts';
  facts.append(
    row('Transmission verdict', report.verdict),
    row('Sanitization state', report.state),
    row('Transmitted', report.transmitted ? 'yes' : 'no'),
    row('Redactions', String(report.redactionCount)),
    row('Text segments', String(report.textSegments)),
    row('Frames verified', String(report.framesVerified)),
    row('Painted surfaces', report.visualSurfaces === undefined ? 'unknown' : String(report.visualSurfaces)),
    row('Capability rung', report.rung),
    row('Observed', ageText),
  );
  if (report.reason) facts.append(row('Reason', report.reason));
  root.append(facts);

  if (report.state === 'UNCERTAIN') {
    const note = el('p', 'Some entity types were below threshold and redacted anyway.', 'detail');
    root.append(note);
  }

  // The non-negotiable statement, restated in the surface itself rather than only
  // in documentation.
  const footer = el('p', '', 'footer');
  footer.textContent =
    'This panel shows counts and verdicts only. It never displays the values it ' +
    'redacted, and neither does any payload.';
  root.append(footer);
}

function renderIdle(message: string): void {
  const root = document.getElementById('report');
  if (!root) return;
  root.textContent = '';
  root.append(el('p', message, 'detail'));
}

chrome.runtime.onMessage.addListener(
  (message: unknown, _sender, sendResponse) => {
    if (!isPanelMessage(message)) return false;
    if (message.kind === 'REPORT') {
      render(message);
      sendResponse({ ok: true });
      return false;
    }
    return false;
  },
);

document.addEventListener('DOMContentLoaded', () => {
  renderIdle('No observation yet. Press Run, or click the toolbar button.');
  const run = document.getElementById('run');
  run?.addEventListener('click', () => {
    void chrome.runtime.sendMessage({ kind: 'RUN' });
  });
  // Ask for whatever the worker already holds, so reopening the panel is not blank.
  void chrome.runtime.sendMessage({ kind: 'REPORT_REQUEST' });
});
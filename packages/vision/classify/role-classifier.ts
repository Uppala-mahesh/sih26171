/**
 * SIH26171 — UI role classification (FR-VIS-1, FR-VIS-4).
 *
 * A structural classifier. It reads DOM facts the browser already knows - tag
 * name, ARIA role, type attribute, geometry, interactivity - and never guesses
 * beyond its evidence.
 *
 * ── The rule that shapes everything here ─────────────────────────────────────
 * FR-VIS-4: an element below the confidence threshold is UNKNOWN, never a
 * best-guess role. A wrong role is worse than a missing one, because a consumer
 * that receives `TEXT_INPUT` will try to type into it, and a consumer that
 * receives UNKNOWN will ask. Guessing converts a detection problem into an
 * action problem, which is where the exfiltration risk lives.
 *
 * ── Why structural and not learned ───────────────────────────────────────────
 * A learned role classifier would need model weights this repository does not
 * ship (see the .gitignore ban on committed weights and DES-ARCH-001's
 * acquisition plan). Rather than fake it with hard-coded confidences that look
 * learned but are not, this uses evidence the browser provides for free. The
 * confidences are therefore calibrated to how deterministic each signal is:
 * an explicit `type=password` is near-certain, an aspect-ratio guess is not.
 */

import type { UiRole } from '../../contracts/payloads.js';

/** FR-VIS-4: below this, the role is UNKNOWN. */
export const CONFIDENCE_THRESHOLD = 0.6;

export interface RoleEvidence {
  readonly tagName: string;
  readonly typeAttribute?: string;
  readonly ariaRole?: string;
  readonly ariaLabel?: string;
  readonly isInteractive: boolean;
  readonly isFocusable: boolean;
  readonly hasChildren: boolean;
  readonly width: number;
  readonly height: number;
  /** Near 1 for a square, 0 for an extreme aspect ratio. */
  readonly aspectRatioCloseness: number;
}

export interface ClassifiedRole {
  readonly role: UiRole;
  readonly confidence: number;
  /** The single signal that decided it. Stated so a wrong call is debuggable. */
  readonly decidedBy: string;
}

/**
 * Map an ARIA role to the FR-VIS-1 taxonomy.
 *
 * `generic`, `none` and `presentation` are deliberately absent: they assert
 * nothing about structure, so forwarding them would pad the taxonomy with
 * entries that carry no information.
 */
const ARIA_MAP: Readonly<Record<string, UiRole>> = {
  button: 'BUTTON',
  textbox: 'TEXT_INPUT',
  searchbox: 'TEXT_INPUT',
  checkbox: 'CHECKBOX',
  radio: 'RADIO',
  combobox: 'SELECT',
  listbox: 'SELECT',
  link: 'LINK',
  menuitem: 'MENU_ITEM',
  tab: 'TAB',
  dialog: 'DIALOG',
  alertdialog: 'DIALOG',
  table: 'TABLE',
  form: 'FORM',
  navigation: 'NAVIGATION',
  img: 'IMAGE',
  text: 'TEXT_REGION',
};

function classifyByTag(e: RoleEvidence): ClassifiedRole | null {
  const tag = e.tagName.toUpperCase();

  if (tag === 'INPUT') {
    const type = (e.typeAttribute ?? 'text').toLowerCase();
    // type=password is the most reliable signal in the entire system: an
    // explicit, machine-readable declaration by the page author, not a
    // heuristic about shape.
    if (type === 'password') {
      return { role: 'PASSWORD_INPUT', confidence: 0.99, decidedBy: 'input[type=password]' };
    }
    if (type === 'checkbox') {
      return { role: 'CHECKBOX', confidence: 0.98, decidedBy: 'input[type=checkbox]' };
    }
    if (type === 'radio') {
      return { role: 'RADIO', confidence: 0.98, decidedBy: 'input[type=radio]' };
    }
    if (type === 'submit' || type === 'button' || type === 'reset') {
      return { role: 'BUTTON', confidence: 0.96, decidedBy: `input[type=${type}]` };
    }
    // A hidden input holds a value the page set programmatically. Calling it a
    // TEXT_INPUT would invite a consumer to type into something invisible.
    if (type === 'hidden') {
      return { role: 'UNKNOWN', confidence: 1, decidedBy: 'input[type=hidden]' };
    }
    return { role: 'TEXT_INPUT', confidence: 0.94, decidedBy: `input[type=${type}]` };
  }

  if (tag === 'TEXTAREA') {
    return { role: 'TEXT_INPUT', confidence: 0.96, decidedBy: 'textarea' };
  }
  if (tag === 'SELECT') {
    return { role: 'SELECT', confidence: 0.97, decidedBy: 'select' };
  }
  if (tag === 'BUTTON') {
    return { role: 'BUTTON', confidence: 0.97, decidedBy: 'button' };
  }
  if (tag === 'A' || tag === 'AREA') {
    return e.hasChildren || e.isInteractive
      ? { role: 'LINK', confidence: 0.9, decidedBy: 'anchor' }
      : { role: 'LINK', confidence: 0.72, decidedBy: 'anchor with weak evidence' };
  }
  if (tag === 'IMG' || tag === 'PICTURE') {
    return { role: 'IMAGE', confidence: 0.95, decidedBy: tag.toLowerCase() };
  }
  if (tag === 'CANVAS' || tag === 'VIDEO') {
    // Opaque by construction: we cannot see into it, and pretending otherwise is
    // FR-PER-7's failure mode.
    return { role: 'IMAGE', confidence: 0.9, decidedBy: `${tag.toLowerCase()} is opaque` };
  }
  if (tag === 'TABLE') return { role: 'TABLE', confidence: 0.95, decidedBy: 'table' };
  if (tag === 'FORM') return { role: 'FORM', confidence: 0.95, decidedBy: 'form' };
  if (tag === 'NAV') return { role: 'NAVIGATION', confidence: 0.93, decidedBy: 'nav' };
  if (tag === 'DIALOG') return { role: 'DIALOG', confidence: 0.94, decidedBy: 'dialog' };

  return null;
}

/**
 * Classify one element.
 *
 * Deterministic and total: always returns a classified role, and the role is
 * UNKNOWN whenever the evidence does not clear the threshold.
 */
export function classifyRole(e: RoleEvidence): ClassifiedRole {
  // 1. An explicit ARIA role outranks everything: the author stated intent.
  const aria = (e.ariaRole ?? '').toLowerCase();
  if (aria && ARIA_MAP[aria]) {
    return { role: ARIA_MAP[aria], confidence: 0.95, decidedBy: `aria-role=${aria}` };
  }

  // 2. Structural tag evidence.
  const byTag = classifyByTag(e);
  if (byTag) return byTag;

  // 3. Geometry, for the generic containers a tag cannot resolve.
  //    Confidence is deliberately LOW and usually below the threshold: aspect
  //    ratio is a weak signal, and it should rarely win.
  if (!e.hasChildren && e.isFocusable && e.aspectRatioCloseness > 0.7 && e.height > 0) {
    return {
      role: 'TEXT_INPUT',
      confidence: 0.52,
      decidedBy: 'focusable, childless, roughly square',
    };
  }
  if (e.isInteractive && !e.hasChildren) {
    return { role: 'BUTTON', confidence: 0.5, decidedBy: 'interactive and childless' };
  }

  return { role: 'UNKNOWN', confidence: 0, decidedBy: 'no signal above threshold' };
}

/** Apply FR-VIS-4: demote anything below the threshold to UNKNOWN. */
export function applyThreshold(c: ClassifiedRole): ClassifiedRole {
  if (c.role !== 'UNKNOWN' && c.confidence < CONFIDENCE_THRESHOLD) {
    return {
      role: 'UNKNOWN',
      confidence: c.confidence,
      decidedBy: `${c.decidedBy} (below threshold)`,
    };
  }
  return c;
}

/** Classify and threshold in one step - the only path callers should use. */
export function classify(e: RoleEvidence): ClassifiedRole {
  return applyThreshold(classifyRole(e));
}


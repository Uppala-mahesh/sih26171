import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * A form field's value lives in `.value`, not in a text node.
 *
 * That distinction caused a real leak: the DOM payload correctly redacted a
 * saved phone number, but because the mask-box sweep only ever read text nodes,
 * an `<input>` contributed no text and therefore earned NO mask box. The DOM
 * was clean while the screenshot -- which is exactly what the vision reasoner
 * receives -- showed the number in the clear.
 *
 * These tests read the REAL shipped source rather than a copy, so they cannot
 * drift away from what actually runs in the page.
 */
const SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../../public/agent-content.js'),
  'utf8',
)

/** The region of walk() that decides whether an element earns a mask box. */
function maskBoxDecisionBlock(): string {
  const start = SOURCE.indexOf("if (protectedField || (smallEnough && hasPii(ownText)))")
  expect(start).toBeGreaterThan(-1)
  return SOURCE.slice(Math.max(0, start - 1200), start + 400)
}

describe('input values reach the mask-box decision', () => {
  it('collects the raw field value while building the observation', () => {
    expect(SOURCE).toContain('let rawFieldValue')
    expect(SOURCE).toMatch(/rawFieldValue\s*=\s*String\(v\)/)
  })

  it('folds the field value into the text the mask decision reads', () => {
    // The bug in one line: ownText stayed empty for every <input>.
    expect(SOURCE).toMatch(/if \(rawFieldValue\) ownText = \(ownText \+ ' ' \+ rawFieldValue\)/)
  })

  it('decides the box using the combined text, not the text-node-only text', () => {
    expect(SOURCE).toContain('hasPii(ownText)')
    const block = maskBoxDecisionBlock()
    expect(block).toContain('rawFieldValue')
  })

  it('records the masked region so the box can be audited by kind', () => {
    expect(SOURCE).toMatch(/if \(rawFieldValue && hasPii\(rawFieldValue\)\)/)
    expect(SOURCE).toMatch(/kind:\s*kindsIn\(rawFieldValue\)\.join\('\+'\)/)
  })

  it('never emits the raw field value into the observation', () => {
    // It may be READ to decide masking, but the emitted field must be the
    // redacted one -- otherwise the leak just moves into the payload.
    const emitted = SOURCE.slice(SOURCE.indexOf('value: value,'))
    expect(emitted).not.toContain('rawFieldValue')
  })
})

describe('the leak this guards against', () => {
  it('a saved phone in an input is detected by the shipped PHONE pattern', () => {
    const phone = SOURCE.split('const PII_PATTERNS = [')[1]
      .split('\n]')[0]
      .split("\n")
      .find((l) => l.includes("type: 'PHONE'"))!
    const re = /regex:\s*(\/.+\/[gimsuy]*)/.exec(phone)![1]
    const last = re.lastIndexOf('/')
    const pattern = new RegExp(re.slice(1, last), re.slice(last + 1))
    expect(pattern.test('+919985186162')).toBe(true)
  })

  it('ordinary account-page chrome is not treated as PII', () => {
    // Over-redaction is a real failure too: masking the nav makes the agent
    // unable to click what it needs.
    const balanced = SOURCE.split('const PII_PATTERNS = [')[1].split('\n]')[0]
    const patterns = [...balanced.matchAll(/regex:\s*(\/.+\/[gimsuy]*)/g)].map((m) => {
      const last = m[1].lastIndexOf('/')
      return new RegExp(m[1].slice(1, last), m[1].slice(last + 1))
    })
    for (const label of [
      'Flights',
      'Become a Seller',
      'My Orders',
      'Saved UPI',
      'Sports, Books & More',
      'What happens when I update my email address (or mobile number)?',
    ]) {
      expect(patterns.some((re) => re.test(label))).toBe(false)
    }
  })
})
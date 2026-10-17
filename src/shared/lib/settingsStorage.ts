import type { UserSettings } from '../types/drishti'

export const DEFAULT_SETTINGS: UserSettings = {
  reasoningEngine: 'auto',
  serverUrl: 'http://127.0.0.1:8787/health',
  privacyMode: 'balanced',
  summaryLanguage: 'en',
}

const STORAGE_KEY = 'drishti_user_settings'

type ChromeWithStorage = {
  storage?: {
    sync?: {
      get: (keys: Record<string, unknown>, callback: (items: Record<string, unknown>) => void) => void
      set: (items: Record<string, unknown>, callback?: () => void) => void
    }
  }
}

declare const chrome: ChromeWithStorage | undefined

function isReasoningEngine(value: unknown): value is UserSettings['reasoningEngine'] {
  return value === 'auto' || value === 'onnx' || value === 'server'
}

function isPrivacyMode(value: unknown): value is UserSettings['privacyMode'] {
  return value === 'strict' || value === 'balanced' || value === 'fast'
}

function isSummaryLanguage(value: unknown): value is UserSettings['summaryLanguage'] {
  return value === 'en' || value === 'hi' || value === 'hinglish'
}

function normalizeSettings(items: Record<string, unknown>): UserSettings {
  return {
    reasoningEngine: isReasoningEngine(items.reasoningEngine)
      ? items.reasoningEngine
      : DEFAULT_SETTINGS.reasoningEngine,
    serverUrl: typeof items.serverUrl === 'string' && items.serverUrl.trim()
      ? items.serverUrl.trim()
      : DEFAULT_SETTINGS.serverUrl,
    privacyMode: isPrivacyMode(items.privacyMode)
      ? items.privacyMode
      : DEFAULT_SETTINGS.privacyMode,
    summaryLanguage: isSummaryLanguage(items.summaryLanguage)
      ? items.summaryLanguage
      : DEFAULT_SETTINGS.summaryLanguage,
  }
}

function hasChromeStorageSync(): boolean {
  return typeof chrome !== 'undefined' && Boolean(chrome?.storage?.sync)
}

export async function loadSettings(): Promise<UserSettings> {
  if (hasChromeStorageSync()) {
    return new Promise((resolve) => {
      try {
        chrome!.storage!.sync!.get(DEFAULT_SETTINGS, (items) => {
          if (items && typeof items === 'object') {
            resolve(normalizeSettings(items))
          } else {
            resolve(DEFAULT_SETTINGS)
          }
        })
      } catch (err) {
        console.warn('[Drishti] Failed to load chrome.storage.sync settings:', err)
        resolve(loadFromLocalStorage())
      }
    })
  }

  return loadFromLocalStorage()
}

export async function saveSettings(partial: Partial<UserSettings>): Promise<UserSettings> {
  const current = await loadSettings()
  const updated: UserSettings = { ...current, ...partial }

  if (hasChromeStorageSync()) {
    return new Promise((resolve) => {
      try {
        chrome!.storage!.sync!.set(updated, () => {
          saveToLocalStorage(updated)
          resolve(updated)
        })
      } catch (err) {
        console.warn('[Drishti] Failed to save to chrome.storage.sync:', err)
        saveToLocalStorage(updated)
        resolve(updated)
      }
    })
  }

  saveToLocalStorage(updated)
  return updated
}

let inMemorySettings: UserSettings | null = null

function loadFromLocalStorage(): UserSettings {
  try {
    if (typeof localStorage !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed: unknown = JSON.parse(stored)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return normalizeSettings(parsed as Record<string, unknown>)
        }
      }
    }
  } catch (err) {
    console.warn('[Drishti] Error reading localStorage:', err)
  }
  return inMemorySettings ? { ...DEFAULT_SETTINGS, ...inMemorySettings } : { ...DEFAULT_SETTINGS }
}

function saveToLocalStorage(settings: UserSettings): void {
  inMemorySettings = { ...settings }
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    }
  } catch (err) {
    console.warn('[Drishti] Error writing to localStorage:', err)
  }
}

export function _resetSettingsForTesting(): void {
  inMemorySettings = null
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.clear()
    }
  } catch (err) {
    console.warn('[Drishti] Error resetting settings:', err)
  }
}

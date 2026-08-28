import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import {
  investmentAssistantEntries,
  evaluationPlatformEntries,
  hasInvalidQuoteChars,
} from '../sidebarEntries'

const __dirname = dirname(fileURLToPath(import.meta.url))
const sidebarSource = readFileSync(
  resolve(__dirname, '../../components/Layout/SidebarMenu.vue'),
  'utf-8'
)

describe('sidebarEntries', () => {
  it('flags full-width quote characters as invalid', () => {
    expect(hasInvalidQuoteChars('index=”/evaluation”')).toBe(true)
    expect(hasInvalidQuoteChars('index="/evaluation"')).toBe(false)
  })

  it('SidebarMenu.vue does not contain any full-width quote characters', () => {
    expect(hasInvalidQuoteChars(sidebarSource)).toBe(false)
  })

  it('SidebarMenu.vue includes an entry for every personal investment assistant path', () => {
    investmentAssistantEntries.forEach((entry) => {
      expect(sidebarSource).toContain(`index="${entry.path}"`)
    })
  })

  it('SidebarMenu.vue includes an entry for every Agent evaluation platform path', () => {
    evaluationPlatformEntries.forEach((entry) => {
      expect(sidebarSource).toContain(`index="${entry.path}"`)
    })
  })

  it('SidebarMenu.vue keeps the /paper entry clickable (regression for the quote bug)', () => {
    expect(sidebarSource).toContain('index="/paper"')
  })
})

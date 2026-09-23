import { describe, expect, it } from 'vitest'
import { brandCssVars, darkenHex, DEFAULT_PRIMARY_COLOR, hasCustomBranding, isValidHexColor } from './branding'

describe('isValidHexColor', () => {
  it('accepts full six-digit hex colors', () => {
    expect(isValidHexColor('#2563eb')).toBe(true)
    expect(isValidHexColor('#ABCDEF')).toBe(true)
  })

  it('rejects shorthand, missing #, and non-hex characters', () => {
    expect(isValidHexColor('#fff')).toBe(false)
    expect(isValidHexColor('2563eb')).toBe(false)
    expect(isValidHexColor('#12345g')).toBe(false)
  })
})

describe('darkenHex', () => {
  it('darkens each channel by the given fraction', () => {
    expect(darkenHex('#ffffff', 0.2)).toBe('#cccccc')
  })

  it('returns the input unchanged when it is not a valid hex color', () => {
    expect(darkenHex('not-a-color')).toBe('not-a-color')
  })
})

describe('brandCssVars', () => {
  it('falls back to the LexProof default when no branding is set', () => {
    expect(brandCssVars(null)).toEqual({
      '--brand-primary': DEFAULT_PRIMARY_COLOR,
      '--brand-primary-hover': darkenHex(DEFAULT_PRIMARY_COLOR, 0.15),
    })
  })

  it('falls back to the default when primary_color is invalid', () => {
    expect(brandCssVars({ primary_color: 'not-a-color' })['--brand-primary']).toBe(DEFAULT_PRIMARY_COLOR)
  })

  it('uses a valid custom primary_color and derives a darker hover shade', () => {
    const vars = brandCssVars({ primary_color: '#7c3aed' })
    expect(vars['--brand-primary']).toBe('#7c3aed')
    expect(vars['--brand-primary-hover']).toBe(darkenHex('#7c3aed', 0.15))
  })
})

describe('hasCustomBranding', () => {
  it('is false when nothing is set', () => {
    expect(hasCustomBranding(null)).toBe(false)
    expect(hasCustomBranding({})).toBe(false)
  })

  it('is true when either field is set', () => {
    expect(hasCustomBranding({ logo_url: 'https://cdn.example.com/logo.png' })).toBe(true)
    expect(hasCustomBranding({ primary_color: '#7c3aed' })).toBe(true)
  })
})

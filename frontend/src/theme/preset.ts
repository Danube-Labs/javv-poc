/**
 * PrimeVue theme bridge — components get their chrome THROUGH the design tokens
 * (ui-foundations: one scale for PrimeVue chrome and custom CSS).
 *
 * primary 500/600 are the exact brand tokens (--coral / --coral-d); the other scale steps are
 * tints/shades of them that PrimeVue needs internally (hover rings, focus washes) — chrome only,
 * never data. Severity/status colors NEVER come from here (tokens.css / tokens.ts own those).
 * The app is single-light-theme by contract: darkModeSelector is disabled.
 */
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

export const JavvPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#fdf3ee',
      100: '#fbe4d9',
      200: '#f6c8b2',
      300: '#f2ab8b',
      400: '#ef9570',
      500: '#ec7e54', /* --coral (exact) */
      600: '#d96a41', /* --coral-d (exact) */
      700: '#b95736',
      800: '#96462c',
      900: '#733622',
      950: '#4a2216',
    },
    colorScheme: {
      light: {
        surface: {
          0: '#ffffff' /* --card */,
          50: '#fbfaf6' /* --panel */,
          100: '#f4f1ea' /* --bg */,
          200: '#f0ebe0' /* --line2 */,
          300: '#e7e0d3' /* --line */,
          400: '#9aa3aa' /* --muted */,
          500: '#64727c' /* --soft */,
          600: '#2c4257' /* --slate3 */,
          700: '#21384a' /* --slate2 */,
          800: '#16232f' /* --slate */,
          900: '#1b2935' /* --ink */,
          950: '#101a22',
        },
      },
    },
  },
})

export const themeOptions = {
  preset: JavvPreset,
  options: {
    prefix: 'p',
    darkModeSelector: false as const,
    cssLayer: false,
  },
}

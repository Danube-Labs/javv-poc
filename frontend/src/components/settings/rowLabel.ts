import type { InjectionKey } from 'vue'

/** What a SettingsRow offers the control inside it: the ids of its title and (if any) hint. */
export interface SettingsRowLabel {
  labelId: string
  hintId: () => string | undefined
}

export const SETTINGS_ROW_LABEL: InjectionKey<SettingsRowLabel> = Symbol('settings-row-label')

import type { AppSettings } from '../../api/settingsApi';

export type SettingsSectionProps = {
  settings: AppSettings;
  onPatch: (patch: AppSettings) => void;
};

function text(value: unknown): string {
  return value == null ? '' : String(value);
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

type InputChangeEvent = {
  currentTarget: HTMLInputElement;
};

export function TelegramSettingsSection({ settings, onPatch }: SettingsSectionProps) {
  return (
    <section className="settings-section" data-section="telegram">
      <h3>Telegram</h3>
      <input value={text(settings.telegram_api_id)} onChange={(event: InputChangeEvent) => onPatch({ telegram_api_id: event.currentTarget.value })} />
      <input value={text(settings.telegram_api_hash)} onChange={(event: InputChangeEvent) => onPatch({ telegram_api_hash: event.currentTarget.value })} />
    </section>
  );
}

export function OpenRouterSettingsSection({ settings, onPatch }: SettingsSectionProps) {
  return (
    <section className="settings-section" data-section="openrouter">
      <h3>OpenRouter / LM Studio</h3>
      <input value={text(settings.openrouter_api_key)} onChange={(event: InputChangeEvent) => onPatch({ openrouter_api_key: event.currentTarget.value })} />
      <input value={text(settings.llm_provider)} onChange={(event: InputChangeEvent) => onPatch({ llm_provider: event.currentTarget.value })} />
      <input value={text(settings.lmstudio_base_url)} onChange={(event: InputChangeEvent) => onPatch({ lmstudio_base_url: event.currentTarget.value })} />
    </section>
  );
}

export function LicenseOverrideSettingsSection({ settings, onPatch }: SettingsSectionProps) {
  return (
    <section className="settings-section" data-section="license-local-override">
      <h3>Локальная лицензия</h3>
      <input
        type="number"
        value={numberValue(settings.local_license_months)}
        onChange={(event: InputChangeEvent) => onPatch({ local_license_months: Number(event.currentTarget.value || 0) })}
      />
      <input
        type="number"
        value={numberValue(settings.local_license_message_limit)}
        onChange={(event: InputChangeEvent) => onPatch({ local_license_message_limit: Number(event.currentTarget.value || 0) })}
      />
    </section>
  );
}

export function ImportLimitsSettingsSection({ settings, onPatch }: SettingsSectionProps) {
  return (
    <section className="settings-section" data-section="import-limits">
      <h3>Импорт</h3>
      <input
        type="number"
        value={numberValue(settings.telegram_import_months)}
        onChange={(event: InputChangeEvent) => onPatch({ telegram_import_months: Number(event.currentTarget.value || 0) })}
      />
      <input
        type="number"
        value={numberValue(settings.telegram_import_message_limit)}
        onChange={(event: InputChangeEvent) => onPatch({ telegram_import_message_limit: Number(event.currentTarget.value || 0) })}
      />
    </section>
  );
}

export function RuntimeStatusSettingsSection({ settings }: { settings: AppSettings }) {
  return (
    <section className="settings-section" data-section="runtime-status">
      <h3>Runtime</h3>
      <dl>
        <dt>Telegram</dt>
        <dd>{text(settings.telegram_api_configured || settings.auth_status || 'unknown')}</dd>
        <dt>OpenRouter</dt>
        <dd>{text(settings.openrouter_configured || settings.llm_provider || 'unknown')}</dd>
      </dl>
    </section>
  );
}

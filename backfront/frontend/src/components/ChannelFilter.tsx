import type { ChannelFilterState } from '../types/channel';

export type ChannelFilterProps = {
  value: ChannelFilterState;
  onChange: (value: ChannelFilterState) => void;
};

const OPTIONS: Array<[keyof ChannelFilterState, string]> = [
  ['showChannels', 'Каналы'],
  ['showGroups', 'Группы'],
  ['showPrivate', 'Личные'],
];

export function ChannelFilter({ value, onChange }: ChannelFilterProps) {
  return (
    <div className="toolbar-group" role="group" aria-label="Фильтры источников">
      {OPTIONS.map(([key, label]) => (
        <label className="chip" key={key}>
          <input
            type="checkbox"
            checked={Boolean(value[key])}
            onChange={(event: { target: { checked: boolean } }) => onChange({ ...value, [key]: event.target.checked })}
          />
          <span>{label}</span>
        </label>
      ))}
    </div>
  );
}

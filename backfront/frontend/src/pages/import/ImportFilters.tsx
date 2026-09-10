export type ImportMembershipFilter = 'not_added' | 'added' | 'all';

export type ImportFiltersProps = {
  query: string;
  membership: ImportMembershipFilter;
  showChannels: boolean;
  showGroups: boolean;
  showPrivate: boolean;
  onQueryChange: (value: string) => void;
  onMembershipChange: (value: ImportMembershipFilter) => void;
  onToggle: (key: 'showChannels' | 'showGroups' | 'showPrivate') => void;
};

export function ImportFilters({
  query,
  membership,
  showChannels,
  showGroups,
  showPrivate,
  onQueryChange,
  onMembershipChange,
  onToggle,
}: ImportFiltersProps) {
  const membershipItems: Array<[ImportMembershipFilter, string]> = [
    ['not_added', 'Не добавленные'],
    ['added', 'Добавленные'],
    ['all', 'Все'],
  ];

  return (
    <section className="import-filter-bar" aria-label="Фильтры импорта">
      <input
        value={query}
        onChange={(event: { currentTarget: HTMLInputElement }) => onQueryChange(event.currentTarget.value)}
        placeholder="Поиск по названию, @username, id"
      />
      <label><input type="checkbox" checked={showChannels} onChange={() => onToggle('showChannels')} /> Каналы</label>
      <label><input type="checkbox" checked={showGroups} onChange={() => onToggle('showGroups')} /> Группы</label>
      <label><input type="checkbox" checked={showPrivate} onChange={() => onToggle('showPrivate')} /> Личные</label>
      <div className="import-membership-tabs">
        {membershipItems.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={membership === value ? 'import-filter-active' : ''}
            onClick={() => onMembershipChange(value)}
          >
            {label}
          </button>
        ))}
      </div>
    </section>
  );
}

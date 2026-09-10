export type ChannelKind = 'channel' | 'group' | 'private' | 'bot' | 'unknown';

export type ChannelFilterState = {
  showChannels: boolean;
  showGroups: boolean;
  showPrivate: boolean;
};

export type ChannelSource = {
  id: string | number;
  selector: string;
  title: string;
  username?: string | null;
  kind: ChannelKind | string;
  messages?: number;
  last_date_utc?: string | null;
};

import { ChatAnalysis } from './ChatAnalysis';
import { ChatMessages } from './ChatMessages';
import { ChatUsers } from './ChatUsers';
import type { ChatAppState } from './types';

export type ChatAppProps = {
  state: ChatAppState;
  onLoadOlder: () => void;
  onRunAnalysis: () => void;
  onRefreshUsers: () => void;
};

export function ChatApp({ state, onLoadOlder, onRunAnalysis, onRefreshUsers }: ChatAppProps) {
  return (
    <main className="chat-app-shell">
      <section className="chat-main">
        <h1>{state.current?.source_selector || state.current?.sender_name || 'Чат'}</h1>
        <ChatMessages messages={state.messages} onLoadOlder={onLoadOlder} />
      </section>
      <aside className="chat-side">
        <ChatAnalysis onRun={onRunAnalysis} progress={null} />
        <ChatUsers users={state.users} page={1} totalPages={1} onPrev={() => undefined} onNext={() => undefined} onRefresh={onRefreshUsers} />
      </aside>
    </main>
  );
}

import type { ChatMessage } from './types';

export type ChatMessagesProps = {
  messages: ChatMessage[];
  onLoadOlder: () => void;
};

export function ChatMessages({ messages, onLoadOlder }: ChatMessagesProps) {
  return (
    <section className="chat-messages" onScroll={() => undefined}>
      <button className="btn btn-ghost" type="button" onClick={onLoadOlder}>
        Загрузить предыдущие
      </button>
      {messages.map((message) => (
        <article className="msg" key={String(message.id)}>
          <div className="msg-meta">
            <span>{message.date_utc || ''}</span>
            <span>{message.sender_username || message.sender_name || message.role || ''}</span>
          </div>
          <div className="msg-text">{message.text || (message.has_media ? '[media]' : '[пустое сообщение]')}</div>
        </article>
      ))}
    </section>
  );
}

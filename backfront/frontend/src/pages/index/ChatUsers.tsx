import type { ChatUser } from './types';

export type ChatUsersProps = {
  users: ChatUser[];
  page: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
  onRefresh: () => void;
};

export function ChatUsers({ users, page, totalPages, onPrev, onNext, onRefresh }: ChatUsersProps) {
  return (
    <section className="chat-users">
      <div className="chat-users-toolbar">
        <button className="btn btn-ghost" type="button" onClick={onRefresh}>Обновить пользователей</button>
        <button className="btn btn-ghost" type="button" onClick={onPrev} disabled={page <= 1}>Назад</button>
        <span className="subtle">{page}/{Math.max(1, totalPages)}</span>
        <button className="btn btn-ghost" type="button" onClick={onNext} disabled={page >= totalPages}>Вперёд</button>
      </div>
      {users.map((user) => (
        <div className="chat-user-row" key={String(user.id)}>
          <strong>{user.title}</strong>
          <span className="subtle">{user.username || ''}</span>
        </div>
      ))}
    </section>
  );
}

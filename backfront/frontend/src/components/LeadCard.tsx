import type { Lead } from '../types/lead';

export type LeadCardProps = {
  lead: Lead;
  active?: boolean;
  onOpen: (lead: Lead) => void;
};

export function LeadCard({ lead, active = false, onOpen }: LeadCardProps) {
  const title = lead.sender_name || lead.sender_username || lead.source_selector || String(lead.id);
  return (
    <button className={`lead-item ${active ? 'lead-row-active' : ''}`} type="button" onClick={() => onOpen(lead)}>
      <div className="lead-head">
        <div>
          <div className="lead-title">{title}</div>
          <div className="lead-meta-line">{lead.updated_at || lead.created_at || ''}</div>
        </div>
      </div>
      <div className="lead-preview text-sm">{lead.text || lead.recommendation || ''}</div>
    </button>
  );
}

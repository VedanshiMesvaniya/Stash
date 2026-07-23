import React from 'react';
import { clamp, money, shortDate } from '../../api';

export default function RecurringCard({ row, currency, onDisable, onEdit }) {
  const progress = clamp(Number(row.progress_percent || 0), 0, 100);
  return (
    <div className="recurring-card">
      <div className="recurring-head">
        <div>
          <div className="transaction-title">{row.name}</div>
          <div className="transaction-sub">
            {row.transaction_type} · next due {shortDate(row.next_due_date)}
          </div>
        </div>
        <div className="status-pill">{row.status}</div>
      </div>
      <div className="recurring-meta">
        <span>{money(row.amount, currency)}</span>
        <span>{row.total_cycles ? `${row.cycles_completed}/${row.total_cycles} cycles` : `${row.cycles_completed} cycles`}</span>
      </div>
      <div className="progress-track" aria-hidden="true">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="recurring-meta subtle">
        <span>{row.category_or_source}</span>
        <span>{Math.round(progress)}%</span>
      </div>
      {onEdit || onDisable ? (
        <div className="recurring-actions">
          {onEdit ? (
            <button className="btn btn-ghost" onClick={() => onEdit(row)}>
              <span className="material-symbols-rounded" aria-hidden="true" style={{ fontSize: 16 }}>edit</span>
              Edit
            </button>
          ) : null}
          {onDisable ? (
            <button className="btn btn-ghost" onClick={() => onDisable(row.id)}>
              Disable
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

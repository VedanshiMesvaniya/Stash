import React from 'react';
import { money } from '../../api';

export default function TimelineItem({ item, currency, actions = null, children = null }) {
  return (
    <div className="transaction-stack">
      <div className="transaction">
        <div>
          <div className="transaction-title">{item.display_label || item.label}</div>
          <div className="transaction-sub">{item.description && item.description !== item.display_label ? item.description : item.date}</div>
        </div>
        <div className="transaction-right">
          <div className={item.type === 'income' ? 'amount-up' : 'amount-down'}>
            {item.type === 'income' ? '+' : '-'} {money(item.amount, currency)}
          </div>
          {actions ? <div className="transaction-actions">{actions}</div> : null}
        </div>
      </div>
      {children ? <div className="transaction-editor">{children}</div> : null}
    </div>
  );
}

import React from 'react';
import { money } from '../../api';

export default function TimelineItem({ item, currency }) {
  return (
    <div className="transaction">
      <div>
        <div className="transaction-title">{item.display_label || item.label}</div>
        <div className="transaction-sub">{item.description && item.description !== item.display_label ? item.description : item.date}</div>
      </div>
      <div className={item.type === 'income' ? 'amount-up' : 'amount-down'}>
        {item.type === 'income' ? '+' : '-'} {money(item.amount, currency)}
      </div>
    </div>
  );
}

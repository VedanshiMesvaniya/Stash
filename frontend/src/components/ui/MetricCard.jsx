import React from 'react';

export default function MetricCard({ label, value, tone }) {
  return (
    <div className="card metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value metric-${tone}`}>{value}</div>
    </div>
  );
}

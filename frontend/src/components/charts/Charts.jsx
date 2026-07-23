import React from 'react';
import { money } from '../../api';

export const PIE_COLORS = ['#4f9d8e', '#74b49b', '#f2a65a', '#e76f51', '#4a90e2', '#7b6fc2', '#c95d87', '#1f7a8c'];

export function PieViz({ entries }) {
  if (!entries.length) {
    return <div className="empty-state">No category data yet.</div>;
  }
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
  let start = 0;
  const segments = entries.map(([label, value], index) => {
    const percent = total ? Number(value || 0) / total : 0;
    const end = start + percent * 360;
    const segment = { label, value, start, end, color: PIE_COLORS[index % PIE_COLORS.length] };
    start = end;
    return segment;
  });

  const gradient = `conic-gradient(${segments.map((segment) => `${segment.color} ${segment.start}deg ${segment.end}deg`).join(', ')})`;

  return (
    <div className="chart-layout">
      <div className="pie-ring" style={{ background: gradient }}>
        <div className="pie-center">{Math.round(total)}</div>
      </div>
      <div className="legend-list">
        {segments.map((segment) => (
          <div className="legend-row" key={segment.label}>
            <span className="legend-swatch" style={{ background: segment.color }} />
            <span className="legend-label">{segment.label}</span>
            <strong>{money(segment.value)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

export function BarViz({ entries }) {
  if (!entries.length) return <div className="empty-state">No category data yet.</div>;
  const max = Math.max(...entries.map(([, value]) => Number(value || 0)), 1);
  return (
    <div className="chart-bars">
      {entries.map(([label, value], index) => (
        <div className="chart-bar-row" key={label}>
          <div className="chart-bar-label">
            <span className="legend-swatch" style={{ background: PIE_COLORS[index % PIE_COLORS.length] }} />
            <span>{label}</span>
          </div>
          <div className="chart-bar-track">
            <div className="chart-bar-fill" style={{ width: `${(Number(value || 0) / max) * 100}%`, background: PIE_COLORS[index % PIE_COLORS.length] }} />
          </div>
          <strong>{money(value)}</strong>
        </div>
      ))}
    </div>
  );
}

export function LineViz({ entries }) {
  if (!entries.length) return <div className="empty-state">No daily trend data yet.</div>;
  const max = Math.max(...entries.map(([, value]) => Number(value || 0)), 1);
  const width = 640;
  const height = 220;
  const points = entries.map(([, value], index) => {
    const x = (index / Math.max(entries.length - 1, 1)) * width;
    const y = height - (Number(value || 0) / max) * (height - 24) - 12;
    return `${x},${y}`;
  });
  const area = `0,${height} ${points.join(' ')} ${width},${height}`;

  return (
    <div className="line-chart">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <polygon points={area} className="line-area" />
        <polyline points={points.join(' ')} className="line-path" />
        {entries.map(([label, value], index) => {
          const x = (index / Math.max(entries.length - 1, 1)) * width;
          const y = height - (Number(value || 0) / max) * (height - 24) - 12;
          return <circle key={label} cx={x} cy={y} r="4" className="line-dot" />;
        })}
      </svg>
      <div className="line-labels">
        {entries.slice(0, 10).map(([label]) => (
          <span key={label}>{label}</span>
        ))}
      </div>
    </div>
  );
}

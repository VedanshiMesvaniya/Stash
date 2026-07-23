import React, { useState } from 'react';
import { money } from '../../api';

export const PIE_COLORS = ['#4f9d8e', '#74b49b', '#f2a65a', '#e76f51', '#4a90e2', '#7b6fc2', '#c95d87', '#1f7a8c'];

// One accent per trend period so the bar chart reads differently at a
// glance depending on the selected range, while staying inside the app's
// existing palette (no colors outside PIE_COLORS/theme accents).
export const TREND_PERIOD_COLORS = {
  weekly: '#4f9d8e',
  monthly: '#f2a65a',
  yearly: '#4a90e2',
};

export function PieViz({ entries }) {
  const [legendOpen, setLegendOpen] = useState(false);
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
    <div className="chart-layout chart-layout-centered">
      <button
        type="button"
        className="pie-info-btn"
        aria-label={legendOpen ? 'Hide legend' : 'Show legend'}
        aria-expanded={legendOpen}
        onClick={() => setLegendOpen((prev) => !prev)}
      >
        <span className="material-symbols-rounded" aria-hidden="true">info</span>
      </button>
      <div className="pie-ring" style={{ background: gradient }}>
        <div className="pie-center">{Math.round(total)}</div>
      </div>
      {legendOpen ? (
        <div className="legend-list legend-list-popover">
          {segments.map((segment) => (
            <div className="legend-row" key={segment.label}>
              <span className="legend-swatch" style={{ background: segment.color }} />
              <span className="legend-label">{segment.label}</span>
              <strong>{money(segment.value)}</strong>
            </div>
          ))}
        </div>
      ) : null}
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

export function TrendBarViz({ entries, period = 'monthly' }) {
  if (!entries.length) return <div className="empty-state">No trend data yet.</div>;
  const color = TREND_PERIOD_COLORS[period] || TREND_PERIOD_COLORS.monthly;
  const max = Math.max(...entries.map(([, value]) => Number(value || 0)), 1);
  return (
    <div className="trend-bars">
      {entries.map(([label, value]) => (
        <div className="trend-bar-col" key={label}>
          <div className="trend-bar-track">
            <div
              className="trend-bar-fill"
              style={{ height: `${(Number(value || 0) / max) * 100}%`, background: color }}
              title={money(value)}
            />
          </div>
          <span className="trend-bar-label">{label}</span>
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

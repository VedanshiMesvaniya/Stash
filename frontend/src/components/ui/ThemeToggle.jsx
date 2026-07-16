import React from 'react';

export default function ThemeToggle({ theme, onThemeChange }) {
  const isDark = theme === 'obsidian';
  return (
    <button className="btn btn-ghost btn-full" type="button" onClick={() => onThemeChange(isDark ? 'mist' : 'obsidian')}>
      <span className="material-symbols-rounded" style={{ fontSize: 18 }}>
        {isDark ? 'light_mode' : 'dark_mode'}
      </span>
      {isDark ? 'Switch to light' : 'Switch to dark'}
    </button>
  );
}

import React from 'react';

export default function ThemeToggle({ theme, onThemeChange }) {
  const isObsidian = theme === 'obsidian' || theme === 'shadow' || theme === 'violet';
  return (
    <button className="btn btn-ghost btn-full" type="button" onClick={() => onThemeChange(isObsidian ? 'mist' : 'obsidian')}>
      {isObsidian ? 'Switch to light' : 'Switch to obsidian'}
    </button>
  );
}

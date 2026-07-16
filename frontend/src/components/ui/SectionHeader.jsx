import React from 'react';

export default function SectionHeader({ title, action }) {
  return (
    <div className="topbar">
      <div>
        <h1 className="page-title">{title}</h1>
      </div>
      {action}
    </div>
  );
}

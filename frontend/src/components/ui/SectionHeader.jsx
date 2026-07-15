import React from 'react';

export default function SectionHeader({ title, copy, action }) {
  return (
    <div className="topbar">
      <div>
        <h1 className="page-title">{title}</h1>
        <p className="page-copy">{copy}</p>
      </div>
      {action}
    </div>
  );
}

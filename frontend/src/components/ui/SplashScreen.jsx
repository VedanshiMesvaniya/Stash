import React from 'react';

export default function SplashScreen() {
  return (
    <div className="splash-screen">
      <div className="splash-card">
        <img src="/static/icons/mark.png" alt="Stash" className="brand-mark" style={{ width: 56, height: 56, borderRadius: 16 }} />
        <div className="brand-wordmark" style={{ fontSize: 22 }}>Stash</div>
        <div className="splash-loader" />
      </div>
    </div>
  );
}

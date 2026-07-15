import React from 'react';

export default function SplashScreen() {
  return (
    <div className="splash-screen">
      <div className="splash-card">
        <img src="/static/icons/FullLogo.png" alt="Stash" className="brand-logo brand-logo-auth" />
        <div className="brand-subtitle">Private finance workspace</div>
        <div className="splash-loader" />
      </div>
    </div>
  );
}

import React, { useEffect, useRef } from 'react';

/**
 * Themed replacement for window.confirm() - the native browser dialog
 * doesn't pick up any of the app's design tokens (dark surface, terracotta
 * accent, Hanken Grotesk), so it looks jarringly out of place against the
 * rest of the UI. This renders as an overlay using the same surface/shadow/
 * radius tokens as the composer's wallet popover, so it reads as part of
 * the app rather than a browser chrome interruption.
 *
 * Controlled component - the parent owns `open` state and passes
 * onConfirm/onCancel. Nothing renders when open is false.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) {
  const confirmButtonRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    confirmButtonRef.current?.focus();
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="confirm-dialog-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onCancel();
    }}
    >
      <div className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
        <h2 id="confirm-dialog-title" className="confirm-dialog-title">{title}</h2>
        {message ? <p className="confirm-dialog-message">{message}</p> : null}
        <div className="confirm-dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            className={`btn ${danger ? 'btn-danger-solid' : 'btn-primary'}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

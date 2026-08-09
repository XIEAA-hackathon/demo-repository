function ConfirmModal({
  open,
  title,
  message,
  confirmText = "Confirm",
  danger = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  return (
    <div className="modal-backdrop">
      <div className="confirm-modal">
        <div className={`modal-icon ${danger ? "danger" : ""}`}>
          {danger ? "!" : "?"}
        </div>

        <span className="eyebrow">ADMIN CONFIRMATION</span>

        <h2>{title}</h2>

        <p>{message}</p>

        <div className="modal-actions">
          <button
            className="secondary-button"
            onClick={onCancel}
          >
            CANCEL
          </button>

          <button
            className={danger ? "danger-button" : "primary-button"}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmModal;
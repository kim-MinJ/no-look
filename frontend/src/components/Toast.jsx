import { useState, useEffect, useCallback } from 'react';

/**
 * Toast notification component
 */
export default function Toast({ toasts, onRemove }) {
    return (
        <div className="toast-container">
            {toasts.map((toast) => (
                <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
            ))}
        </div>
    );
}

function ToastItem({ toast, onRemove }) {
    const [isVisible, setIsVisible] = useState(false);

    useEffect(() => {
        setTimeout(() => setIsVisible(true), 10);

        const timer = setTimeout(() => {
            setIsVisible(false);
            setTimeout(() => onRemove(toast.id), 300);
        }, 3000);

        return () => clearTimeout(timer);
    }, [toast.id, onRemove]);

    return (
        <div className={`toast ${toast.type} ${isVisible ? 'visible' : ''}`}>
            <span className="toast-icon">{toast.type === 'success' ? '✓' : '✕'}</span>
            <span className="toast-message">{toast.message}</span>
            <button
                className="toast-close"
                onClick={() => {
                    setIsVisible(false);
                    setTimeout(() => onRemove(toast.id), 300);
                }}
            >
                ×
            </button>
        </div>
    );

}

/**
 * Hook for managing toasts
 */
export function useToast() {
    const [toasts, setToasts] = useState([]);

    // ✅ 함수 참조 고정 (렌더 때마다 addToast가 바뀌는 문제 방지)
    const addToast = useCallback((message, type = 'success') => {
        const id = Date.now();
        setToasts((prev) => [...prev, { id, message, type }]);
    }, []);

    const removeToast = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    return { toasts, addToast, removeToast };
}

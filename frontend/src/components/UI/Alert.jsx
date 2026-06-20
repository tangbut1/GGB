import React, { useState, useEffect, useCallback } from 'react';
import { X, AlertTriangle, AlertCircle, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';

const iconMap = {
  error:    <AlertCircle size={18} className="text-danger" />,
  warning:  <AlertTriangle size={18} className="text-warning" />,
  success:  <CheckCircle2 size={18} className="text-success" />,
};

const bgMap = {
  error:    'bg-danger/10 border-danger/30',
  warning:  'bg-warning/10 border-warning/30',
  success:  'bg-success/10 border-success/30',
};

export default function Alert() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((e) => {
    const { type = 'error', message = '' } = e.detail || {};
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, type, message }]);
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);

  useEffect(() => {
    window.addEventListener('app:toast', addToast);
    return () => window.removeEventListener('app:toast', addToast);
  }, [addToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast, idx) => (
        <div
          key={toast.id}
          className={clsx(
            'pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm',
            'animate-slideIn min-w-[280px] max-w-[420px]',
            bgMap[toast.type] || bgMap.error
          )}
          style={{ animationDelay: `${idx * 50}ms` }}
        >
          <div className="shrink-0 mt-0.5">
            {iconMap[toast.type] || iconMap.error}
          </div>
          <p className="flex-1 text-sm text-text-main leading-snug pr-2">
            {toast.message}
          </p>
          <button
            onClick={() => setToasts(prev => prev.filter(t => t.id !== toast.id))}
            className="shrink-0 p-0.5 rounded-md text-text-secondary hover:text-text-main hover:bg-white/5 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      ))}
      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(-12px) translateX(20px); }
          to   { opacity: 1; transform: translateY(0) translateX(0); }
        }
        .animate-slideIn {
          animation: slideIn 0.2s ease-out;
        }
        @media (prefers-reduced-motion: reduce) {
          .animate-slideIn {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

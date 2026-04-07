import { useState } from 'react';

interface UpgradeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function UpgradeModal({ isOpen, onClose }: UpgradeModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpgrade = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setError('Not authenticated. Please log in first.');
        setLoading(false);
        return;
      }

      const res = await fetch('/api/payments/create-checkout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to create checkout session');
      }

      const data = await res.json();
      if (data.session_url || data.checkout_url) {
        // Redirect to Stripe checkout
        window.location.href = data.session_url || data.checkout_url;
      } else {
        throw new Error('No checkout URL returned');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Network error';
      setError(message);
      console.error('Upgrade error:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-white">🚀 Upgrade to Pro</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-300 text-2xl"
          >
            ×
          </button>
        </div>

        <p className="text-slate-300 text-sm mb-6">
          You've used all 3 free scans this month. Upgrade to Pro for unlimited scans, resume optimization, and priority support.
        </p>

        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 mb-6">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-3xl font-bold text-white">$9.99</span>
            <span className="text-slate-400">/month</span>
          </div>
          <p className="text-sm text-slate-400">Cancel anytime, no questions asked</p>
        </div>

        <div className="space-y-3 mb-6">
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400">✓</span>
            <span>Unlimited monthly analyses</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400">✓</span>
            <span>AI-optimized resume text</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400">✓</span>
            <span>Download optimized resume (DOCX)</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400">✓</span>
            <span>Priority support</span>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        <div className="space-y-3">
          <button
            onClick={handleUpgrade}
            disabled={loading}
            className="w-full bg-gradient-to-r from-emerald-600 to-cyan-600 text-white font-semibold py-3 rounded-lg hover:shadow-lg hover:shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? 'Redirecting to Stripe...' : 'Upgrade to Pro Now'}
          </button>
          <button
            onClick={onClose}
            disabled={loading}
            className="w-full text-slate-300 py-2 rounded-lg hover:bg-slate-800/50 disabled:opacity-50 transition-colors"
          >
            Maybe later
          </button>
        </div>

        <p className="text-xs text-slate-500 text-center mt-4">
          Secure payment powered by Stripe
        </p>
      </div>
    </div>
  );
}

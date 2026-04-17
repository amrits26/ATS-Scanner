import { useState } from 'react';

interface UpgradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  scansUsed?: number;
  scanLimit?: number;
}

export default function UpgradeModal({ isOpen, onClose, scansUsed = 3, scanLimit = 3 }: UpgradeModalProps) {
  const [loading, setLoading] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
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

  const handleStartTrial = async () => {
    setTrialLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setError('Not authenticated. Please log in first.');
        setTrialLoading(false);
        return;
      }

      const res = await fetch('/api/trial/start', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start trial');
      }

      const data = await res.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Network error';
      setError(message);
    } finally {
      setTrialLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-white">Get Hired 3x Faster</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-300 text-2xl"
          >
            ×
          </button>
        </div>

        {/* Progress tracker + social proof */}
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mb-4">
          <p className="text-sm text-amber-200 font-medium">
            You've used {scansUsed}/{scanLimit} free scans.
          </p>
          <p className="text-xs text-amber-300/80 mt-1">
            78% of Pro users land interviews within 14 days.
          </p>
        </div>

        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 mb-5">
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-3xl font-bold text-white">$9.99</span>
            <span className="text-slate-400">/month</span>
          </div>
          <p className="text-xs text-emerald-400 font-medium">
            Less than one coffee a week — pays for itself with one interview.
          </p>
        </div>

        <div className="space-y-2.5 mb-5">
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span><strong className="text-white">Unlimited</strong> ATS analyses — no monthly cap</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>AI-optimized resume — <strong className="text-white">average +24 ATS points</strong></span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Download polished DOCX — ready to submit</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Keyword gap analysis with fix suggestions</span>
          </div>
        </div>

        {/* Social proof */}
        <div className="flex items-center gap-2 mb-5 px-3 py-2 bg-slate-800/40 rounded-lg">
          <span className="text-yellow-400 text-xs">★★★★★</span>
          <p className="text-xs text-slate-400">
            <strong className="text-slate-300">4.8/5</strong> from 2,300+ users who improved their score
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg">
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        <div className="space-y-2.5">
          <button
            onClick={handleStartTrial}
            disabled={trialLoading || loading}
            className="w-full bg-gradient-to-r from-emerald-600 to-cyan-600 text-white font-semibold py-3 rounded-lg hover:shadow-lg hover:shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {trialLoading ? 'Starting trial...' : 'Try Pro Free for 7 Days'}
          </button>
          <button
            onClick={handleUpgrade}
            disabled={loading || trialLoading}
            className="w-full border border-slate-600 text-slate-300 font-medium py-2.5 rounded-lg hover:bg-slate-800/50 disabled:opacity-50 transition-colors text-sm"
          >
            {loading ? 'Redirecting...' : 'Subscribe Now — $9.99/mo'}
          </button>
          <button
            onClick={onClose}
            disabled={loading || trialLoading}
            className="w-full text-slate-500 py-2 rounded-lg hover:text-slate-400 disabled:opacity-50 transition-colors text-xs"
          >
            Maybe later
          </button>
        </div>

        <p className="text-xs text-slate-500 text-center mt-4">
          Cancel anytime. Secure payment powered by Stripe.
        </p>
      </div>
    </div>
  );
}

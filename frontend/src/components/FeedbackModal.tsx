import { useState } from 'react';

interface FeedbackModalProps {
  isOpen: boolean;
  sessionId: string;
  onClose: () => void;
}

export function FeedbackModal({ isOpen, sessionId, onClose }: FeedbackModalProps) {
  const [accuracy, setAccuracy] = useState(3);
  const [helpful, setHelpful] = useState(true);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/analysis/${sessionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          score_accuracy: accuracy,
          was_helpful: helpful,
          user_notes: notes || undefined
        })
      });

      if (response.ok) {
        setSubmitted(true);
        setTimeout(() => onClose(), 1500);
      } else {
        console.error('Feedback submission failed');
      }
    } catch (err) {
      console.error('Error submitting feedback:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 max-w-md w-full shadow-2xl">
        {!submitted ? (
          <>
            <h2 className="text-xl font-bold text-white mb-2">How accurate was this analysis?</h2>
            <p className="text-slate-400 text-sm mb-6">Your feedback helps us improve the AI model.</p>

            {/* Accuracy Scale 1-5 */}
            <div className="flex gap-2 mb-6 justify-center">
              {[1, 2, 3, 4, 5].map(score => (
                <button
                  key={score}
                  onClick={() => setAccuracy(score)}
                  className={`w-10 h-10 rounded-lg font-bold transition-all ${
                    accuracy === score
                      ? 'bg-emerald-600 text-white scale-110 shadow-lg shadow-emerald-500/50'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                  }`}
                  title={`Rating: ${score}/5`}
                >
                  {score}
                </button>
              ))}
            </div>

            {/* Helpful Buttons */}
            <div className="flex gap-3 mb-4">
              <button
                onClick={() => setHelpful(true)}
                className={`flex-1 py-2 rounded-lg font-semibold transition-all ${
                  helpful
                    ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-500/30'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                👍 Helpful
              </button>
              <button
                onClick={() => setHelpful(false)}
                className={`flex-1 py-2 rounded-lg font-semibold transition-all ${
                  !helpful
                    ? 'bg-red-600 text-white shadow-lg shadow-red-500/30'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                👎 Not Helpful
              </button>
            </div>

            {/* Notes */}
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Why? Tell us how we can improve... (optional)"
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white text-sm mb-4 h-20 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:border-transparent"
            />

            {/* Submit Button */}
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="w-full bg-gradient-to-r from-emerald-600 to-cyan-600 text-white font-bold py-2 rounded-lg hover:from-emerald-700 hover:to-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-emerald-500/30"
            >
              {loading ? 'Sending...' : 'Send Feedback'}
            </button>

            <button
              onClick={onClose}
              className="w-full text-slate-400 text-sm mt-2 hover:text-slate-300 transition-colors"
            >
              Skip
            </button>
          </>
        ) : (
          <div className="text-center py-8">
            <div className="text-4xl mb-3">🎉</div>
            <h3 className="text-lg font-bold text-emerald-400 mb-2">Thank you!</h3>
            <p className="text-slate-400 text-sm">The machine is learning from your feedback.</p>
          </div>
        )}
      </div>
    </div>
  );
}

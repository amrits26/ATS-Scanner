/**
 * TailorRewriteModal.tsx
 * 
 * Modal CTA for users to purchase Tailor Agent rewrite ($29 one-time).
 * Displayed when ATS score is 50-75 (room for improvement).
 */

import React, { useState } from 'react';

interface TailorRewriteModalProps {
  isOpen: boolean;
  onClose: () => void;
  resumeText: string;
  atsScore: number;
  jobDescription?: string;
  userEmail: string;
}

export const TailorRewriteModal: React.FC<TailorRewriteModalProps> = ({
  isOpen,
  onClose,
  resumeText,
  atsScore,
  jobDescription = '',
  userEmail,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleRewriteClick = async () => {
    if (!jobDescription || !userEmail) {
      setError('Job description and email are required');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/tailor/rewrite-for-job', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(localStorage.getItem('authToken') && {
            'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
          }),
        },
        body: JSON.stringify({
          resume_text: resumeText,
          job_description: jobDescription,
          email: userEmail,
          job_title: 'Target Job',
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to initiate rewrite');
      }

      const data = await response.json();
      
      // Redirect to Stripe checkout
      if (data.stripe_url) {
        window.location.href = data.stripe_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4 p-6">
        {/* Header */}
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-2xl font-bold text-gray-800">
            🚀 Tailor Your Resume
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl"
          >
            ×
          </button>
        </div>

        {/* Current Score Display */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
          <p className="text-gray-700 text-sm">Current ATS Score</p>
          <p className="text-3xl font-bold text-blue-600">{atsScore}/100</p>
          <p className="text-xs text-gray-600 mt-1">Room for improvement</p>
        </div>

        {/* Benefits */}
        <div className="mb-6 space-y-2">
          <h3 className="font-semibold text-gray-800 mb-3">What you'll get:</h3>
          <ul className="space-y-2">
            <li className="flex items-start gap-2">
              <span className="text-green-600 font-bold mt-0.5">✓</span>
              <span className="text-gray-700 text-sm">Full resume rewrite tailored to this job description</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-600 font-bold mt-0.5">✓</span>
              <span className="text-gray-700 text-sm">See your estimated ATS score improvement</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-600 font-bold mt-0.5">✓</span>
              <span className="text-gray-700 text-sm">Download as DOCX (7-day access)</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-600 font-bold mt-0.5">✓</span>
              <span className="text-gray-700 text-sm">AI-powered keyword matching & metrics</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-600 font-bold mt-0.5">✓</span>
              <span className="text-gray-700 text-sm">3 alternative summary options</span>
            </li>
          </ul>
        </div>

        {/* Score Increase Guarantee Badge */}
        <div className="bg-emerald-50 border-2 border-emerald-300 rounded-lg p-3 mb-4 flex items-center gap-3">
          <div className="bg-emerald-100 rounded-full p-2 flex-shrink-0">
            <svg className="w-5 h-5 text-emerald-600" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
            </svg>
          </div>
          <div>
            <p className="text-emerald-800 font-semibold text-sm">Score Increase Guarantee</p>
            <p className="text-emerald-700 text-xs">ATS score improves or your money back — no questions asked.</p>
          </div>
        </div>

        {/* Price */}
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 text-center">
          <p className="text-gray-700 text-sm">One-time investment</p>
          <p className="text-4xl font-bold text-green-600">$29</p>
          <p className="text-xs text-gray-600">Secure payment via Stripe</p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition"
          >
            Not Now
          </button>
          <button
            onClick={handleRewriteClick}
            disabled={isLoading}
            className="flex-1 px-4 py-2 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:from-blue-700 hover:to-blue-800 disabled:from-gray-400 disabled:to-gray-400 font-medium transition"
          >
            {isLoading ? 'Processing...' : 'Get Tailored Resume'}
          </button>
        </div>

        {/* Footer */}
        <p className="text-xs text-gray-500 text-center mt-4">
          💳 Secure payment. Money-back guarantee if unsatisfied.
        </p>
      </div>
    </div>
  );
};

export default TailorRewriteModal;

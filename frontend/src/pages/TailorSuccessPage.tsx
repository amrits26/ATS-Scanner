/**
 * TailorSuccessPage.tsx
 * 
 * Shows after successful Stripe payment.
 * Polls for rewrite completion, displays download link when ready.
 * Route: /tailor-rewrite/{sessionId}
 */

import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ResumeComparison } from '../ResomeComparison';

interface RewriteStatus {
  status: 'pending' | 'processing' | 'complete' | 'failed';
  download_url?: string;
  before_score?: number;
  after_score?: number;
  score_lift?: number;
  resume_text?: string;
  rewritten_resume_text?: string;
}

export const TailorSuccessPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [status, setStatus] = useState<RewriteStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollingCount, setPollingCount] = useState(0);
  const [showDiff, setShowDiff] = useState(false);

  useEffect(() => {
    const pollForCompletion = async () => {
      try {
        const response = await fetch(`/api/tailor/rewrite-status/${sessionId}`);

        if (!response.ok) {
          if (response.status === 404) {
            setError('Rewrite session not found. Please check your email for updates.');
            return;
          }
          throw new Error('Failed to check status');
        }

        const data: RewriteStatus = await response.json();
        setStatus(data);
        setIsLoading(false);

        if (data.status === 'complete' || data.status === 'failed') {
          // Stop pollocking has completed or failed
          return;
        }

        // Continue polling every 2 seconds if still processing
        if (pollingCount < 30) {
          // Max 60 seconds of polling
          setPollingCount((prev) => prev + 1);
          setTimeout(pollForCompletion, 2000);
        } else {
          setError('Rewrite is taking longer than expected. Please check your email.');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
        setIsLoading(false);
      }
    };

    pollForCompletion();
  }, [sessionId]);

  // Pending/Processing state
  if (isLoading || (status && status.status === 'processing')) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
        <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full text-center">
          <div className="mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 animate-pulse">
              <svg className="w-8 h-8 text-blue-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </div>
          </div>

          <h2 className="text-2xl font-bold text-gray-800 mb-2">
            ✨ Generating Your Resume
          </h2>
          <p className="text-gray-600 mb-4">
            Our AI is tailoring your resume for maximum impact.
          </p>
          <p className="text-sm text-gray-500">
            This usually takes 30-60 seconds. You can close this tab—we'll email you when it's ready.
          </p>

          {/* Progress indicator */}
          <div className="mt-6">
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-blue-600 to-indigo-600 w-2/3 animate-pulse"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Success state
  if (status && status.status === 'complete' && status.download_url) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex flex-col items-center px-4 py-12">
        <div className="bg-white rounded-lg shadow-2xl p-8 w-full max-w-md">
          {/* Success Icon */}
          <div className="flex justify-center mb-6">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-green-100">
              <svg className="w-10 h-10 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
          </div>

          <h2 className="text-2xl font-bold text-gray-800 mb-2 text-center">
            Your Resume is Ready! 🎉
          </h2>

          {/* Score Improvement */}
          {status.before_score !== undefined && status.after_score !== undefined && (
            <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg p-4 mb-6">
              <p className="text-gray-700 text-sm mb-2">ATS Score Improvement</p>
              <div className="flex items-center justify-between">
                <div className="text-center flex-1">
                  <p className="text-2xl font-bold text-gray-400">{status.before_score}</p>
                  <p className="text-xs text-gray-500">Before</p>
                </div>
                <div className="text-2xl text-green-600 font-bold px-4">→</div>
                <div className="text-center flex-1">
                  <p className="text-2xl font-bold text-green-600">{status.after_score}</p>
                  <p className="text-xs text-gray-500">After</p>
                </div>
              </div>
              {status.score_lift !== undefined && (
                <p className="text-center mt-2 text-sm font-semibold text-green-600">
                  +{status.score_lift} point improvement 🚀
                </p>
              )}
            </div>
          )}

          {/* Download Button */}
          <a
            href={status.download_url}
            download
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-700 hover:to-emerald-700 font-semibold transition mb-3"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download Your Resume (DOCX)
          </a>

          {/* Additional Info */}
          <div className="space-y-2 text-sm text-gray-600 mb-4">
            <p className="flex items-start gap-2">
              <span className="text-blue-600 font-bold">💡</span>
              <span>Use this resume for your next application to this job</span>
            </p>
            <p className="flex items-start gap-2">
              <span className="text-yellow-600 font-bold">⏰</span>
              <span>Download link expires in 7 days</span>
            </p>
            <p className="flex items-start gap-2">
              <span className="text-purple-600 font-bold">📧</span>
              <span>Check your email for a detailed summary</span>
            </p>
          </div>

          {/* CTA */}
          <div className="flex gap-2">
            {status.resume_text && status.rewritten_resume_text && (
              <button
                onClick={() => setShowDiff(!showDiff)}
                className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium transition"
              >
                {showDiff ? 'Hide' : 'View'} Changes
              </button>
            )}
            <button
              onClick={() => window.location.href = '/'}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition"
            >
              Back to Dashboard
            </button>
          </div>
        </div>

        {/* Diff View */}
        {showDiff && status.resume_text && status.rewritten_resume_text && (
          <div className="bg-slate-900 rounded-lg shadow-2xl p-6 w-full max-w-5xl mt-8">
            <h3 className="text-lg font-semibold text-white mb-4">What Changed in Your Resume</h3>
            <ResumeComparison
              original={status.resume_text}
              optimized={status.rewritten_resume_text}
            />
          </div>
        )}
      </div>
    );
  }

  // Error state
  if (status && status.status === 'failed') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-pink-100 flex items-center justify-center px-4">
        <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full text-center">
          <div className="mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-100">
              <svg className="w-8 h-8 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
          </div>

          <h2 className="text-2xl font-bold text-gray-800 mb-2">
            Oops! Something went wrong
          </h2>
          <p className="text-gray-600 mb-6">
            We couldn't generate your resume. Please try again or contact support.
          </p>

          <div className="space-y-2">
            <button
              onClick={() => window.location.reload()}
              className="w-full px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium transition"
            >
              Try Again
            </button>
            <button
              onClick={() => window.location.href = '/support'}
              className="w-full px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition"
            >
              Contact Support
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Generic error
  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-pink-100 flex items-center justify-center px-4">
        <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full text-center">
          <p className="text-red-600 font-semibold mb-4">{error}</p>
          <button
            onClick={() => window.location.href = '/'}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return null;
};

export default TailorSuccessPage;

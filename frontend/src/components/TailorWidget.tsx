// frontend/src/components/TailorWidget.tsx
import React, { useState } from 'react';
import { RefreshCw, Loader2, CheckCircle, AlertCircle, Copy } from 'lucide-react';

interface TailorResult {
  rewritten_resume: string;
  key_alignments: string[];
  match_score: number;
  execution_time_seconds: number;
  gemini_cost_cents: number;
}

export const TailorWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [jobUrl, setJobUrl] = useState('');
  const [jobText, setJobText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TailorResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<'url' | 'text'>('url');

  const handleTailor = async () => {
    if (!jobUrl.trim() && !jobText.trim()) {
      setError('Please provide either a job URL or paste the job description.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const resumeText = localStorage.getItem('current_resume') || '';
      if (!resumeText) {
        setError('Please upload a resume first to use Auto-Tailor.');
        setIsLoading(false);
        return;
      }

      const response = await fetch('/api/agent/tailor', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        body: JSON.stringify({
          resume_text: resumeText,
          jd_url: inputMode === 'url' ? jobUrl : undefined,
          jd_text: inputMode === 'text' ? jobText : undefined,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to tailor resume.';
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const copyResumeToClipboard = () => {
    if (result?.rewritten_resume) {
      navigator.clipboard.writeText(result.rewritten_resume);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <>
      {/* Modal Trigger */}
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white rounded-lg shadow-md transition-all hover:scale-105"
      >
        <RefreshCw size={18} />
        <span>Tailor for This Job</span>
      </button>

      {/* Modal */}
      {isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 p-6 border-b bg-gradient-to-r from-purple-600 to-purple-700 text-white flex justify-between items-center">
              <div>
                <h2 className="text-2xl font-bold">Auto-Tailor Your Resume</h2>
                <p className="text-sm opacity-90">Optimize your resume for this specific job in seconds</p>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="text-white hover:bg-white hover:bg-opacity-20 p-2 rounded-lg transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Content */}
            <div className="p-6 space-y-6">
              {!result ? (
                <>
                  {/* Input Mode Selector */}
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        value="url"
                        checked={inputMode === 'url'}
                        onChange={(e) => setInputMode(e.target.value as 'url' | 'text')}
                        className="w-4 h-4"
                      />
                      <span className="text-sm font-medium">Paste Job URL</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        value="text"
                        checked={inputMode === 'text'}
                        onChange={(e) => setInputMode(e.target.value as 'url' | 'text')}
                        className="w-4 h-4"
                      />
                      <span className="text-sm font-medium">Paste Job Description</span>
                    </label>
                  </div>

                  {/* Input */}
                  {inputMode === 'url' ? (
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Job Post URL</label>
                      <input
                        type="url"
                        value={jobUrl}
                        onChange={(e) => setJobUrl(e.target.value)}
                        placeholder="https://www.linkedin.com/jobs/view/123456789/"
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                        disabled={isLoading}
                      />
                      <p className="text-xs text-gray-500 mt-1">We'll extract the job description from the link</p>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Paste Job Description</label>
                      <textarea
                        value={jobText}
                        onChange={(e) => setJobText(e.target.value)}
                        placeholder="Senior Software Engineer at Google. We're looking for someone with 5+ years of experience in JavaScript, React, Node.js..."
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 h-32 resize-none"
                        disabled={isLoading}
                      />
                    </div>
                  )}

                  {error && (
                    <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex gap-3">
                      <AlertCircle className="text-red-600 flex-shrink-0" size={20} />
                      <p className="text-sm text-red-700">{error}</p>
                    </div>
                  )}

                  {/* CTA */}
                  <button
                    onClick={handleTailor}
                    disabled={isLoading || (!jobUrl.trim() && !jobText.trim())}
                    className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white font-semibold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="animate-spin" size={20} />
                        <span>Tailoring your resume...</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw size={20} />
                        <span>Tailor My Resume</span>
                      </>
                    )}
                  </button>

                  <p className="text-xs text-gray-500 text-center">⏱️ Usually takes 10-15 seconds</p>
                </>
              ) : (
                <>
                  {/* Results */}
                  <div className="space-y-6">
                    {/* Match Score */}
                    <div className="p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border border-blue-200">
                      <p className="text-sm text-gray-600 mb-2">ATS Match Score</p>
                      <div className="flex items-center gap-4">
                        <div className={`text-5xl font-bold ${getScoreColor(result.match_score)}`}>
                          {result.match_score}%
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            {result.match_score >= 80 ? (
                              <CheckCircle className="text-green-600" size={20} />
                            ) : (
                              <AlertCircle className="text-yellow-600" size={20} />
                            )}
                            <p className="text-sm text-gray-700">
                              {result.match_score >= 80
                                ? 'Great alignment with the job!'
                                : 'Good alignment, but some improvements possible.'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Key Alignments */}
                    {result.key_alignments.length > 0 && (
                      <div>
                        <h3 className="font-semibold text-gray-900 mb-3">Key Alignments Made</h3>
                        <ul className="space-y-2">
                          {result.key_alignments.map((alignment, i) => (
                            <li key={i} className="flex items-start gap-3 p-2 bg-green-50 rounded border border-green-200">
                              <CheckCircle className="text-green-600 flex-shrink-0 mt-0.5" size={18} />
                              <span className="text-sm text-gray-700">{alignment}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Rewritten Resume */}
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-3">Your Tailored Resume</h3>
                      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 max-h-48 overflow-y-auto">
                        <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                          {result.rewritten_resume.substring(0, 500)}...
                        </pre>
                      </div>
                      <button
                        onClick={copyResumeToClipboard}
                        className="mt-3 w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                      >
                        <Copy size={16} />
                        Copy Full Resume
                      </button>
                    </div>

                    {/* Metrics */}
                    <div className="flex gap-3 text-xs text-gray-500 px-4 py-2 bg-gray-50 rounded">
                      <span>⏱️ {result.execution_time_seconds.toFixed(1)}s</span>
                      <span>💰 ${(result.gemini_cost_cents / 100).toFixed(3)}</span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      onClick={() => setResult(null)}
                      className="px-4 py-2 border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition-colors"
                    >
                      Try Another Job
                    </button>
                    <button
                      onClick={() => setIsOpen(false)}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors"
                    >
                      Done
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default TailorWidget;

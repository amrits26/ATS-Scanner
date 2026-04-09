// frontend/src/components/InterviewPrepWidget.tsx
import React, { useState } from 'react';
import { Briefcase, Loader2, Copy, Download, AlertCircle } from 'lucide-react';

interface InterviewQuestion {
  question: string;
  answer: string;
}

interface InterviewResult {
  questions: {
    technical: string[];
    behavioral: string[];
    culture_fit: string[];
    resume_specific: string[];
  };
  star_answers: Record<string, string>;
  execution_time_seconds: number;
  gemini_cost_cents: number;
}

export const InterviewPrepWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [jobTitle, setJobTitle] = useState('');
  const [company, setCompany] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<InterviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState<'technical' | 'behavioral' | 'culture_fit' | 'resume_specific'>('technical');

  const handleGenerate = async () => {
    if (!jobTitle.trim() || !company.trim()) {
      setError('Please provide both job title and company.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const resumeText = localStorage.getItem('current_resume') || '';
      if (!resumeText) {
        setError('Please upload a resume first to use Interview Prep.');
        setIsLoading(false);
        return;
      }

      const response = await fetch('/api/agent/interview-prep', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
        body: JSON.stringify({
          job_title: jobTitle,
          company: company,
          resume_text: resumeText,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to generate interview prep.';
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const copyQuestion = (question: string) => {
    navigator.clipboard.writeText(question);
  };

  const downloadAsPDF = () => {
    if (!result) return;
    // Placeholder for PDF generation
    console.log('Download as PDF:', result);
  };

  const getQuestions = () => {
    if (!result?.questions) return [];
    return result.questions[selectedTab] || [];
  };

  return (
    <>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 text-white rounded-lg shadow-md transition-all hover:scale-105"
      >
        <Briefcase size={18} />
        <span>Interview Prep</span>
      </button>

      {/* Modal */}
      {isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 p-6 border-b bg-gradient-to-r from-indigo-600 to-indigo-700 text-white flex justify-between items-center">
              <div>
                <h2 className="text-2xl font-bold">AI Interview Prep</h2>
                <p className="text-sm opacity-90">Get role-specific questions and STAR answer templates</p>
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
                  {/* Form */}
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Job Title</label>
                      <input
                        type="text"
                        value={jobTitle}
                        onChange={(e) => setJobTitle(e.target.value)}
                        placeholder="e.g., Senior Software Engineer, Product Manager, Data Scientist"
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        disabled={isLoading}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">Company</label>
                      <input
                        type="text"
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        placeholder="e.g., Google, Meta, Apple, Netflix"
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        disabled={isLoading}
                      />
                    </div>
                  </div>

                  {error && (
                    <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex gap-3">
                      <AlertCircle className="text-red-600 flex-shrink-0" size={20} />
                      <p className="text-sm text-red-700">{error}</p>
                    </div>
                  )}

                  {/* CTA */}
                  <button
                    onClick={handleGenerate}
                    disabled={isLoading || !jobTitle.trim() || !company.trim()}
                    className="w-full px-6 py-3 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 text-white font-semibold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="animate-spin" size={20} />
                        <span>Generating questions...</span>
                      </>
                    ) : (
                      <>
                        <Briefcase size={20} />
                        <span>Generate Interview Questions</span>
                      </>
                    )}
                  </button>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="p-3 bg-blue-50 rounded border border-blue-200">
                      <p className="font-semibold text-blue-900">15+ Questions</p>
                      <p className="text-xs text-blue-700">Technical, behavioral, culture fit + more</p>
                    </div>
                    <div className="p-3 bg-green-50 rounded border border-green-200">
                      <p className="font-semibold text-green-900">STAR Templates</p>
                      <p className="text-xs text-green-700">Ready-to-use answer structures</p>
                    </div>
                  </div>

                  <p className="text-xs text-gray-500 text-center">✨ Powered by AI • Personalized to your resume</p>
                </>
              ) : (
                <>
                  {/* Results */}
                  <div className="space-y-6">
                    {/* Tabs */}
                    <div className="flex gap-2 border-b">
                      {(['technical', 'behavioral', 'culture_fit', 'resume_specific'] as const).map((tab) => (
                        <button
                          key={tab}
                          onClick={() => setSelectedTab(tab)}
                          className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
                            selectedTab === tab
                              ? 'border-indigo-600 text-indigo-600'
                              : 'border-transparent text-gray-600 hover:text-gray-900'
                          }`}
                        >
                          {tab === 'culture_fit' ? 'Culture' : tab.charAt(0).toUpperCase() + tab.slice(1).replace('_', ' ')}
                        </button>
                      ))}
                    </div>

                    {/* Questions List */}
                    <div className="space-y-4">
                      {getQuestions().map((question, idx) => (
                        <div key={idx} className="p-4 bg-gradient-to-br from-indigo-50 to-blue-50 rounded-lg border border-indigo-200">
                          <div className="flex justify-between items-start gap-3 mb-3">
                            <div className="flex-1">
                              <p className="font-semibold text-gray-900">
                                {idx + 1}. {question}
                              </p>
                            </div>
                            <button
                              onClick={() => copyQuestion(question)}
                              className="p-2 hover:bg-white rounded transition-colors flex-shrink-0"
                              title="Copy question"
                            >
                              <Copy size={16} className="text-gray-600" />
                            </button>
                          </div>

                          {/* STAR Answer Template */}
                          {result.star_answers && result.star_answers[question] && (
                            <div className="p-3 bg-white rounded border-l-4 border-indigo-600">
                              <p className="text-xs font-semibold text-gray-600 mb-2">STAR Answer Template:</p>
                              <p className="text-sm text-gray-700 whitespace-pre-wrap">
                                {result.star_answers[question]}
                              </p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Metrics */}
                    <div className="flex gap-3 text-xs text-gray-500 px-4 py-2 bg-gray-50 rounded">
                      <span>⏱️ {result.execution_time_seconds.toFixed(1)}s</span>
                      <span>💰 ${(result.gemini_cost_cents / 100).toFixed(3)}</span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="grid grid-cols-3 gap-3">
                    <button
                      onClick={downloadAsPDF}
                      className="px-4 py-2 border border-indigo-600 hover:bg-indigo-50 text-indigo-600 font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                    >
                      <Download size={16} />
                      Export PDF
                    </button>
                    <button
                      onClick={() => setResult(null)}
                      className="px-4 py-2 border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition-colors"
                    >
                      New Role
                    </button>
                    <button
                      onClick={() => setIsOpen(false)}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors"
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

export default InterviewPrepWidget;

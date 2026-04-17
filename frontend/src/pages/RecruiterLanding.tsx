import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function RecruiterLanding() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const preselectedTier = searchParams.get('tier') || 'basic';

  const [email, setEmail] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [fullName, setFullName] = useState('');
  const [selectedTier, setSelectedTier] = useState(preselectedTier);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !companyName) {
      setError('Email and company name are required');
      return;
    }
    setLoading(true);
    setError('');

    try {
      const res = await fetch(`${API_BASE}/api/recruiter-marketplace/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          company_name: companyName,
          full_name: fullName || undefined,
          tier: selectedTier,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Signup failed');
      }

      const data = await res.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      {/* Hero */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24">
        <div className="text-center">
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-gray-900 tracking-tight">
            Hire Candidates Who Are{' '}
            <span className="text-indigo-600">Already Optimized</span> for Your Job
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-gray-600 max-w-3xl mx-auto">
            Stop screening 200+ generic applications. Our AI pre-screens candidates
            against your exact job description and surfaces only the top 5% match.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row justify-center gap-4">
            <a
              href="#signup"
              className="inline-flex items-center justify-center px-8 py-4 bg-indigo-600 text-white font-semibold rounded-lg shadow-lg hover:bg-indigo-700 transition"
            >
              Start 7-Day Free Trial
              <svg className="ml-2 w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </a>
            <a
              href="#pricing"
              className="inline-flex items-center justify-center px-8 py-4 bg-white text-gray-700 font-semibold rounded-lg border border-gray-300 hover:bg-gray-50 transition"
            >
              View Pricing
            </a>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
          <div className="bg-white p-8 rounded-2xl shadow-sm border text-center">
            <div className="text-4xl font-bold text-indigo-600">48h</div>
            <div className="text-gray-600 mt-2">Average Time to First Interview</div>
          </div>
          <div className="bg-white p-8 rounded-2xl shadow-sm border text-center">
            <div className="text-4xl font-bold text-indigo-600">87%</div>
            <div className="text-gray-600 mt-2">Match Accuracy vs. Manual Screening</div>
          </div>
          <div className="bg-white p-8 rounded-2xl shadow-sm border text-center">
            <div className="text-4xl font-bold text-indigo-600">5.2h</div>
            <div className="text-gray-600 mt-2">Saved Per Job Posting</div>
          </div>
        </div>
      </div>

      {/* How It Works */}
      <div className="bg-gray-50 py-16 sm:py-20">
        <div className="max-w-7xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-12">How It Works</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
            {[
              { step: '1', title: 'Post Your Job', desc: 'Enter your job description once. Our AI extracts key requirements and skills.' },
              { step: '2', title: 'Candidates Optimize', desc: 'Job seekers use our platform to tailor their resumes specifically for your role.' },
              { step: '3', title: 'Receive Top Matches', desc: 'Get a curated feed of the top 5% candidates, scored and ready to interview.' },
            ].map(({ step, title, desc }) => (
              <div key={step} className="text-center">
                <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <span className="text-2xl font-bold text-indigo-600">{step}</span>
                </div>
                <h3 className="text-xl font-semibold mb-2">{title}</h3>
                <p className="text-gray-600">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pricing */}
      <div id="pricing" className="max-w-7xl mx-auto px-4 py-16 sm:py-20">
        <h2 className="text-3xl font-bold text-center mb-12">Simple, Transparent Pricing</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          {/* Basic */}
          <div
            className={`bg-white p-8 rounded-2xl shadow-lg border-2 cursor-pointer transition ${
              selectedTier === 'basic' ? 'border-indigo-400 ring-2 ring-indigo-200' : 'border-gray-200'
            }`}
            onClick={() => setSelectedTier('basic')}
          >
            <h3 className="text-2xl font-bold mb-2">Basic</h3>
            <div className="text-4xl font-bold mb-1">
              $99<span className="text-lg font-normal text-gray-500">/mo</span>
            </div>
            <p className="text-sm text-gray-500 mb-6">7-day free trial included</p>
            <ul className="space-y-3 text-gray-700">
              {['Up to 10 active job postings', 'View top matches per job', '5 candidate unlocks / month', 'Email match alerts'].map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm">
                  <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                  </svg>
                  {f}
                </li>
              ))}
            </ul>
          </div>

          {/* Pro */}
          <div
            className={`p-8 rounded-2xl shadow-lg border-2 relative cursor-pointer transition ${
              selectedTier === 'pro' ? 'bg-indigo-50 border-indigo-500 ring-2 ring-indigo-200' : 'bg-indigo-50/50 border-indigo-200'
            }`}
            onClick={() => setSelectedTier('pro')}
          >
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white px-4 py-1 rounded-full text-xs font-semibold">
              Most Popular
            </div>
            <h3 className="text-2xl font-bold mb-2">Pro</h3>
            <div className="text-4xl font-bold mb-1">
              $299<span className="text-lg font-normal text-gray-500">/mo</span>
            </div>
            <p className="text-sm text-gray-500 mb-6">7-day free trial included</p>
            <ul className="space-y-3 text-gray-700">
              {['Unlimited job postings', 'Unlimited candidate matches', 'Unlimited candidate unlocks', 'Priority support', 'Advanced analytics dashboard'].map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm">
                  <svg className="w-5 h-5 text-green-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                  </svg>
                  {f}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Signup Form */}
      <div id="signup" className="bg-gray-50 py-16 sm:py-20">
        <div className="max-w-md mx-auto px-4">
          <h2 className="text-3xl font-bold text-center mb-8">Get Started</h2>

          <form onSubmit={handleSignup} className="bg-white rounded-2xl shadow-lg p-8 space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Work Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
              <input
                type="text"
                required
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Acme Corp"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Your Name (optional)</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Jane Smith"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Plan</label>
              <select
                value={selectedTier}
                onChange={(e) => setSelectedTier(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="basic">Basic — $99/mo</option>
                <option value="pro">Pro — $299/mo</option>
              </select>
            </div>

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition"
            >
              {loading ? 'Creating account...' : `Start 7-Day Free Trial — ${selectedTier === 'pro' ? '$299' : '$99'}/mo after`}
            </button>

            <p className="text-xs text-gray-500 text-center">
              Cancel anytime during trial. No charge for 7 days.
            </p>
          </form>
        </div>
      </div>

      {/* Footer */}
      <div className="max-w-7xl mx-auto px-4 py-12 text-center">
        <p className="text-sm text-gray-500">
          Already have an account?{' '}
          <button onClick={() => navigate('/recruiter')} className="text-indigo-600 hover:underline font-medium">
            Go to Dashboard
          </button>
        </p>
      </div>
    </div>
  );
}

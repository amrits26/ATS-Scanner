import React, { useState, useEffect } from 'react';
import { MapPin, DollarSign, ArrowRight, Loader, Copy, Download, Check, Globe, Briefcase, Filter, Search } from 'lucide-react';

interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  country: string;
  countryCode: string;
  salary: { min: number; max: number; currency: string };
  visaSponsorship: boolean;
  description: string;
  url: string;
  postedDate: string;
}

interface TailoredResult {
  sessionId: string;
  status: 'loading' | 'completed' | 'error';
  rewrittenResume: string;
  keyAlignments: string[];
  matchScore: number;
  executionTimeSeconds: number;
  geminiCostCents: number;
}

// Mock jobs data
const MOCK_JOBS: Job[] = [
  {
    id: '1',
    title: 'Senior Android Engineer',
    company: 'Leonardo.AI',
    location: 'Sydney, NSW',
    country: 'Australia',
    countryCode: 'AU',
    salary: { min: 130000, max: 160000, currency: 'AUD' },
    visaSponsorship: true,
    description: 'Senior Android Engineer with 8+ years experience. Must know Kotlin, MVVM architecture, and Jetpack libraries. Experience with high-scale apps preferred.',
    url: 'https://glassdoor.com',
    postedDate: '2 days ago',
  },
  {
    id: '2',
    title: 'Android Developer',
    company: 'RFA Group',
    location: 'Brisbane, QLD',
    country: 'Australia',
    countryCode: 'AU',
    salary: { min: 140000, max: 180000, currency: 'AUD' },
    visaSponsorship: true,
    description: 'Full-stack mobile development. React Native and Kotlin. Remote-friendly. Need CI/CD and Firebase experience.',
    url: 'https://linkedin.com',
    postedDate: '1 week ago',
  },
  {
    id: '3',
    title: 'Senior Android Engineer (Kotlin)',
    company: 'Canva',
    location: 'Toronto, ON',
    country: 'Canada',
    countryCode: 'CA',
    salary: { min: 150000, max: 200000, currency: 'CAD' },
    visaSponsorship: true,
    description: 'Join platform engineering team. Expert-level Kotlin. Performance optimization critical. System design background required.',
    url: 'https://careers.canva.com',
    postedDate: '3 days ago',
  },
  {
    id: '4',
    title: 'Android Developer',
    company: 'Pinterest',
    location: 'San Francisco, CA',
    country: 'USA',
    countryCode: 'US',
    salary: { min: 180000, max: 220000, currency: 'USD' },
    visaSponsorship: true,
    description: 'Work on Pinterest mobile app. Large-scale infrastructure. Need expertise in reactive programming, RxJava, and performance optimization.',
    url: 'https://careers.pinterest.com',
    postedDate: '4 days ago',
  },
];

// Radial gauge component
function RadialGauge({ score, label, size = 120 }: { score: number; label: string; size?: number }) {
  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (Math.max(0, Math.min(score, 100)) / 100) * circumference;

  const getColor = (s: number) => {
    if (s >= 75) return '#10b981';
    if (s >= 50) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={45} fill="none" stroke="#334155" strokeWidth="8" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={45}
          fill="none"
          stroke={getColor(score)}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-500"
        />
      </svg>
      <div className="text-center -mt-16">
        <div className="text-3xl font-bold text-white">{Math.round(score)}</div>
        <div className="text-xs text-slate-400 mt-1">{label}</div>
      </div>
    </div>
  );
}

// Country flag emoji
function CountryFlag({ countryCode }: { countryCode: string }) {
  const flags: Record<string, string> = {
    AU: '🇦🇺',
    US: '🇺🇸',
    CA: '🇨🇦',
    UK: '🇬🇧',
    NZ: '🇳🇿',
    SG: '🇸🇬',
    DE: '🇩🇪',
  };
  return <span className="text-xl">{flags[countryCode] || '🌍'}</span>;
}

export const JobHunterDashboard: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>(MOCK_JOBS);
  const [selectedJob, setSelectedJob] = useState<Job>(MOCK_JOBS[0]);
  const [tailoredResult, setTailoredResult] = useState<TailoredResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [filterCountry, setFilterCountry] = useState<string>('');
  const [filterVisa, setFilterVisa] = useState(false);
  const [copied, setCopied] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  // Mock user resume
  const mockResume = `JOHN DOE
Senior Software Engineer | 8+ years Android Development

PROFESSIONAL SUMMARY
Experienced Android engineer with 8+ years building high-scale mobile applications. Expert in Kotlin, MVVM architecture, and Jetpack libraries.

EXPERIENCE
Senior Android Engineer, TechCorp (2021-Present)
• Led Android team of 5 engineers, shipped 3 major features serving 5M+ users
• Improved app performance by 40%, reduced crashes by 60%
• Implemented MVVM architecture using LiveData and Room database
• Mentored junior engineers, conducted code reviews, established best practices

Android Developer, StartupXYZ (2018-2021)
• Developed and maintained flagship Android app (5M+ downloads)
• Implemented Jetpack Compose for modern UI development
• Built real-time features using WebSockets and Firebase
• Optimized app size from 45MB to 28MB using ProGuard

SKILLS
Languages: Kotlin, Java, Python, C++
Technologies: Android SDK, Jetpack, Kotlin Coroutines, RxJava, Retrofit, Room, Firebase
Architecture: MVVM, Clean Architecture, MVI Pattern
Tools: Git, Jira, Jenkins, GitHub Actions, Firebase Console

EDUCATION
BS Computer Science, State University (2015)`;

  // Filter jobs
  const filteredJobs = jobs.filter(job => {
    if (filterCountry && job.countryCode !== filterCountry) return false;
    if (filterVisa && !job.visaSponsorship) return false;
    if (searchTerm && !job.title.toLowerCase().includes(searchTerm.toLowerCase()) && !job.company.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  // Handle job selection and auto-tailor
  const handleJobSelect = async (job: Job) => {
    setSelectedJob(job);
    setTailoredResult({
      sessionId: '',
      status: 'loading',
      rewrittenResume: '',
      keyAlignments: [],
      matchScore: 0,
      executionTimeSeconds: 0,
      geminiCostCents: 0,
    });
    setLoading(true);

    try {
      const token = localStorage.getItem('auth_token');
      if (!token) throw new Error('Not authenticated');
      const response = await fetch('/api/agent/tailor', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          resume_text: mockResume,
          jd_text: job.description,
          job_url: job.url,
        }),
      });

      if (!response.ok) throw new Error('Tailor failed');
      const data = await response.json();

      setTailoredResult({
        sessionId: data.session_id,
        status: 'completed',
        rewrittenResume: data.rewritten_resume || 'Your resume tailored for this role...',
        keyAlignments: data.key_alignments || [],
        matchScore: data.match_score || 0,
        executionTimeSeconds: data.execution_time_seconds || 0,
        geminiCostCents: data.gemini_cost_cents || 0,
      });
    } catch (err) {
      console.error('Tailor error:', err);
      setTailoredResult({
        sessionId: '',
        status: 'error',
        rewrittenResume: 'Failed to generate tailored resume. Please try again.',
        keyAlignments: [],
        matchScore: 0,
        executionTimeSeconds: 0,
        geminiCostCents: 0,
      });
    } finally {
      setLoading(false);
    }
  };

  // Copy to clipboard
  const copyToClipboard = () => {
    navigator.clipboard.writeText(tailoredResult?.rewrittenResume || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const countries = ['', ...new Set(jobs.map(j => j.countryCode))];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-4xl font-bold text-white flex items-center gap-3">
              <Briefcase className="text-emerald-400" size={32} />
              AI Job Hunter
            </h1>
            <p className="text-slate-400 mt-2">Find roles • Auto-tailor your resume • Land interviews</p>
          </div>
        </div>

        {/* Search & Filters */}
        <div className="space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-3 text-slate-400" size={18} />
            <input
              type="text"
              placeholder="Search jobs by title, company..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 rounded-lg bg-slate-700/50 border border-slate-600 text-white text-sm placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
            />
          </div>

          <div className="flex gap-3 flex-wrap">
            <select
              value={filterCountry}
              onChange={(e) => setFilterCountry(e.target.value)}
              className="px-4 py-2 rounded-lg bg-slate-700/50 border border-slate-600 text-white text-sm hover:bg-slate-600/50 transition-colors cursor-pointer"
            >
              <option value="">All Countries</option>
              {countries.map(
                code =>
                  code && (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  )
              )}
            </select>

            <label className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-700/50 border border-slate-600 text-white text-sm cursor-pointer hover:bg-slate-600/50 transition-colors">
              <input type="checkbox" checked={filterVisa} onChange={(e) => setFilterVisa(e.target.checked)} className="w-4 h-4" />
              Visa Sponsorship
            </label>

            <div className="ml-auto text-slate-400 text-sm flex items-center gap-2">
              <Filter size={16} />
              {filteredJobs.length} role{filteredJobs.length !== 1 ? 's' : ''} found
            </div>
          </div>
        </div>
      </div>

      {/* Main Content: Two-Panel Layout */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel: Job List */}
        <div className="lg:col-span-1">
          <div className="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden backdrop-blur sticky top-6">
            <div className="p-4 border-b border-slate-700 bg-slate-900/50">
              <h2 className="font-semibold text-white text-sm flex items-center gap-2">
                <Briefcase size={16} />
                Available Roles
              </h2>
            </div>
            <div className="divide-y divide-slate-700 max-h-[calc(100vh-200px)] overflow-y-auto">
              {filteredJobs.map(job => (
                <div
                  key={job.id}
                  onClick={() => handleJobSelect(job)}
                  className={`p-4 cursor-pointer transition-all ${
                    selectedJob.id === job.id ? 'bg-emerald-500/20 border-l-2 border-emerald-400' : 'hover:bg-slate-700/30 border-l-2 border-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-semibold text-white text-sm">{job.title}</h3>
                      <p className="text-xs text-slate-400">{job.company}</p>
                    </div>
                    <CountryFlag countryCode={job.countryCode} />
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 text-xs text-slate-300">
                      <MapPin size={12} />
                      {job.location}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-300">
                      <DollarSign size={12} />
                      {job.salary.min.toLocaleString()}-{job.salary.max.toLocaleString()} {job.salary.currency}
                    </div>
                    {job.visaSponsorship && (
                      <div className="inline-flex items-center gap-1 px-2 py-1 bg-emerald-500/20 text-emerald-300 text-xs rounded border border-emerald-500/30 mt-2">
                        <Globe size={10} />
                        Visa Sponsor
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Panel: Job Details & Tailored Resume */}
        <div className="lg:col-span-2 space-y-6">
          {/* Selected Job Header */}
          <div className="bg-gradient-to-r from-emerald-500/10 to-cyan-500/10 border border-emerald-500/30 rounded-xl p-6 backdrop-blur">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold text-white">{selectedJob.title}</h2>
                <p className="text-slate-400 mt-1">
                  {selectedJob.company} • {selectedJob.location}
                </p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-emerald-400">${selectedJob.salary.max.toLocaleString()}</div>
                <p className="text-xs text-slate-400">{selectedJob.salary.currency} / year</p>
              </div>
            </div>
            <a
              href={selectedJob.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-emerald-400 hover:text-emerald-300 text-sm font-medium transition-colors"
            >
              View Full Job Listing
              <ArrowRight size={14} />
            </a>
          </div>

          {/* Match Score Section */}
          {tailoredResult && (
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6 backdrop-blur">
              <h3 className="text-lg font-semibold text-white mb-6">Tailored Resume Match</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="flex flex-col items-center">
                  <RadialGauge score={tailoredResult.matchScore} label="Match Score" size={100} />
                </div>

                <div className="flex flex-col justify-center">
                  <div className="bg-slate-700/30 rounded-lg p-4 space-y-3">
                    <p className="text-xs text-slate-400 font-semibold mb-3">KEY ALIGNMENTS</p>
                    {tailoredResult.keyAlignments.slice(0, 3).map((align, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-slate-200">
                        <Check size={14} className="text-emerald-400 mt-0.5 flex-shrink-0" />
                        <span className="line-clamp-2">{align}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex flex-col justify-center">
                  <div className="bg-slate-700/30 rounded-lg p-4 space-y-4">
                    <div>
                      <p className="text-xs text-slate-400">Generation Time</p>
                      <p className="text-lg font-semibold text-white">{tailoredResult.executionTimeSeconds.toFixed(1)}s</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-400">AI Cost</p>
                      <p className="text-sm font-semibold text-emerald-400">${(tailoredResult.geminiCostCents / 100).toFixed(3)}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tailored Resume Preview */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden backdrop-blur flex flex-col">
            <div className="p-4 bg-slate-900/50 border-b border-slate-700 flex items-center justify-between sticky top-0">
              <h3 className="font-semibold text-white text-sm">Your Tailored Resume</h3>
              <div className="flex gap-2">
                <button
                  onClick={copyToClipboard}
                  className="flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 text-xs font-medium rounded transition-colors"
                >
                  {copied ? (
                    <>
                      <Check size={14} className="text-emerald-400" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy size={14} />
                      Copy
                    </>
                  )}
                </button>
                <button className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 text-xs font-medium rounded transition-colors">
                  <Download size={14} />
                  PDF
                </button>
              </div>
            </div>
            <div className="p-6 max-h-96 overflow-y-auto flex-1">
              {loading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="text-center">
                    <Loader className="animate-spin mx-auto mb-2 text-emerald-400" size={24} />
                    <p className="text-sm text-slate-400">Tailoring your resume for this role...</p>
                  </div>
                </div>
              ) : tailoredResult?.status === 'completed' ? (
                <div className="text-sm text-slate-300 whitespace-pre-wrap font-mono text-xs leading-relaxed">
                  {tailoredResult.rewrittenResume}
                </div>
              ) : (
                <div className="text-center py-8 text-slate-400">
                  <p>Select a job to generate a tailored resume</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default JobHunterDashboard;

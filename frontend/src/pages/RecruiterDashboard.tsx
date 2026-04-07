import React, { useState } from 'react';
import axios from 'axios';

interface Lead {
  id: string;
  user_id: string;
  ats_score: number;
  matched_skills: string[];
  missing_skills: string[];
  job_title: string;
  experience_years: number;
  location_state: string;
  resume_snippet: string;
  created_at: string;
  unlock_status: 'available' | 'pending_payment' | 'unlocked' | 'hired';
  unlock_expires_at?: string;
}

interface Stats {
  total_unlocks: number;
  total_hires: number;
  amount_spent: number;
  amount_earned: number;
  recent_hires: Array<{
    candidate_id: string;
    hire_date: string;
  }>;
}

interface LeadsResponse {
  leads: Lead[];
  total: number;
  page: number;
  limit: number;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function RecruiterDashboard() {
  const [recruiterEmail, setRecruiterEmail] = useState('');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Filters
  const [skillsFilter, setSkillsFilter] = useState('');
  const [locationFilter, setLocationFilter] = useState('');
  const [minScoreFilter, setMinScoreFilter] = useState(85);
  const [daysOldFilter, setDaysOldFilter] = useState(30);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalLeads, setTotalLeads] = useState(0);
  const [leadsPerPage] = useState(20);

  // UI State
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [showResumeModal, setShowResumeModal] = useState(false);
  const [fullResume, setFullResume] = useState('');
  const [resumeLoading, setResumeLoading] = useState(false);
  const [hiringLead, setHiringLead] = useState<string | null>(null);
  const [hireDateInput, setHireDateInput] = useState('');

  // Login handler
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recruiterEmail.trim()) {
      setError('Please enter your email');
      return;
    }

    setIsLoggedIn(true);
    setError('');
    await Promise.all([fetchLeads(), fetchStats()]);
  };

  // Fetch leads with filters
  const fetchLeads = async (page = 1) => {
    try {
      setLoading(true);
      setError('');

      const skills = skillsFilter
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s);

      const params = new URLSearchParams({
        recruiter_email: recruiterEmail,
        page: page.toString(),
        limit: leadsPerPage.toString(),
        min_score: minScoreFilter.toString(),
        days_old: daysOldFilter.toString(),
      });

      if (locationFilter) params.append('location_state', locationFilter);
      if (skills.length > 0) params.append('skills', skills.join(','));

      const response = await axios.get<LeadsResponse>(`${API_BASE}/api/recruiter/leads?${params}`);

      setLeads(response.data.leads);
      setTotalLeads(response.data.total);
      setCurrentPage(page);
    } catch (err) {
      setError(`Failed to fetch leads: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  // Fetch recruiter stats
  const fetchStats = async () => {
    try {
      const response = await axios.get<Stats>(
        `${API_BASE}/api/recruiter/stats?recruiter_email=${recruiterEmail}`
      );
      setStats(response.data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  };

  // View full resume (after unlock)
  const viewFullResume = async (lead: Lead) => {
    if (lead.unlock_status !== 'unlocked') {
      setError('You must unlock this candidate first');
      return;
    }

    try {
      setResumeLoading(true);
      const response = await axios.get(
        `${API_BASE}/api/recruiter/unlocked/${lead.id}?recruiter_email=${recruiterEmail}`
      );
      setFullResume(response.data.resume_text || 'Resume content not available');
      setSelectedLead(lead);
      setShowResumeModal(true);
    } catch (err) {
      setError(`Failed to fetch resume: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setResumeLoading(false);
    }
  };

  // Unlock candidate (Stripe checkout)
  const unlockCandidate = async (lead: Lead) => {
    try {
      setLoading(true);
      const response = await axios.post(`${API_BASE}/api/recruiter/unlock/${lead.id}`, {
        recruiter_email: recruiterEmail,
      });

      // Redirect to Stripe checkout
      if (response.data.checkoutUrl) {
        window.location.href = response.data.checkoutUrl;
      } else if (response.data.sessionId) {
        // Alternative: Stripe JS integration (if setup)
        window.location.href = `https://checkout.stripe.com/pay/${response.data.sessionId}`;
      }
    } catch (err) {
      setError(`Failed to unlock candidate: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  // Report hire
  const reportHire = async (lead: Lead) => {
    if (!hireDateInput) {
      setError('Please enter a hire date');
      return;
    }

    try {
      setLoading(true);
      await axios.post(`${API_BASE}/api/recruiter/hire_report`, {
        candidate_id: lead.id,
        recruiter_email: recruiterEmail,
        hire_date: hireDateInput,
      });

      setError('');
      setHiringLead(null);
      setHireDateInput('');

      // Refresh stats and leads
      await Promise.all([fetchLeads(currentPage), fetchStats()]);

      // Show success message
      setTimeout(() => {
        setError('');
      }, 3000);
    } catch (err) {
      setError(`Failed to report hire: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  // Apply filters
  const handleFilterApply = () => {
    setCurrentPage(1);
    fetchLeads(1);
  };

  // Pagination
  const totalPages = Math.ceil(totalLeads / leadsPerPage);

  if (!isLoggedIn) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-900 to-purple-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-md">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">Recruiter Portal</h1>
          <p className="text-gray-600 mb-6">Access candidates from ATS Scanner</p>

          <form onSubmit={handleLogin}>
            <input
              type="email"
              placeholder="Enter your email"
              value={recruiterEmail}
              onChange={(e) => setRecruiterEmail(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg transition"
            >
              Access Dashboard
            </button>
          </form>

          {error && <p className="text-red-600 text-sm mt-4">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="container mx-auto px-4 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold text-gray-800">Recruiter Dashboard</h1>
              <p className="text-gray-600">{recruiterEmail}</p>
            </div>
            <button
              onClick={() => setIsLoggedIn(false)}
              className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition"
            >
              Logout
            </button>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-8">
        {/* Stats Grid */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-gray-600 text-sm">Unlocks</p>
              <p className="text-3xl font-bold text-blue-600">{stats.total_unlocks}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-gray-600 text-sm">Hires</p>
              <p className="text-3xl font-bold text-green-600">{stats.total_hires}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-gray-600 text-sm">Spent</p>
              <p className="text-3xl font-bold text-red-600">${(stats.amount_spent / 100).toFixed(2)}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-gray-600 text-sm">Earned</p>
              <p className="text-3xl font-bold text-yellow-600">${(stats.amount_earned / 100).toFixed(2)}</p>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Filters</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <input
              type="text"
              placeholder="Skills (comma-separated)"
              value={skillsFilter}
              onChange={(e) => setSkillsFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="text"
              placeholder="Location (e.g., CA, TX)"
              maxLength={2}
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value.toUpperCase())}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div>
              <label className="text-sm text-gray-600">Min ATS Score</label>
              <input
                type="range"
                min="0"
                max="100"
                value={minScoreFilter}
                onChange={(e) => setMinScoreFilter(parseInt(e.target.value))}
                className="w-full"
              />
              <p className="text-sm text-gray-700">{minScoreFilter}/100</p>
            </div>
            <div>
              <label className="text-sm text-gray-600">Days Old</label>
              <input
                type="number"
                min="1"
                value={daysOldFilter}
                onChange={(e) => setDaysOldFilter(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              onClick={handleFilterApply}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg transition disabled:opacity-50"
            >
              Apply Filters
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg mb-6">{error}</div>}

        {/* Leads List */}
        <div className="space-y-4">
          {loading && <p className="text-center text-gray-600">Loading...</p>}

          {!loading && leads.length === 0 && (
            <div className="bg-white rounded-lg shadow p-8 text-center">
              <p className="text-gray-600">No candidates found matching your filters</p>
            </div>
          )}

          {leads.map((lead) => (
            <div key={lead.id} className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-800">{lead.job_title}</h3>
                  <p className="text-gray-600 text-sm">{lead.location_state}</p>
                </div>
                <div className="text-right">
                  <p className={`text-2xl font-bold ${lead.ats_score >= 85 ? 'text-green-600' : 'text-yellow-600'}`}>
                    {lead.ats_score}
                  </p>
                  <p className="text-gray-600 text-xs">ATS Score</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 mb-4 text-sm">
                <div>
                  <p className="text-gray-600">Experience</p>
                  <p className="font-semibold">{lead.experience_years}+ years</p>
                </div>
                <div>
                  <p className="text-gray-600">Status</p>
                  <p className="font-semibold capitalize">{lead.unlock_status.replace('_', ' ')}</p>
                </div>
              </div>

              <div className="mb-4">
                <p className="text-gray-600 text-sm mb-2">Matched Skills</p>
                <div className="flex flex-wrap gap-2">
                  {lead.matched_skills.slice(0, 5).map((skill, i) => (
                    <span key={i} className="bg-green-100 text-green-800 px-3 py-1 rounded-full text-sm">
                      {skill}
                    </span>
                  ))}
                  {lead.matched_skills.length > 5 && (
                    <span className="bg-gray-100 text-gray-800 px-3 py-1 rounded-full text-sm">
                      +{lead.matched_skills.length - 5} more
                    </span>
                  )}
                </div>
              </div>

              <p className="text-gray-700 text-sm mb-4 line-clamp-3">{lead.resume_snippet}</p>

              <div className="flex gap-2 flex-wrap">
                {lead.unlock_status === 'available' && (
                  <button
                    onClick={() => unlockCandidate(lead)}
                    disabled={loading}
                    className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg transition disabled:opacity-50"
                  >
                    Unlock for $5
                  </button>
                )}

                {lead.unlock_status === 'unlocked' && (
                  <>
                    <button
                      onClick={() => viewFullResume(lead)}
                      disabled={resumeLoading}
                      className="bg-purple-600 hover:bg-purple-700 text-white font-bold py-2 px-4 rounded-lg transition disabled:opacity-50"
                    >
                      View Resume
                    </button>
                    {hiringLead !== lead.id && (
                      <button
                        onClick={() => setHiringLead(lead.id)}
                        className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-lg transition"
                      >
                        Report Hire
                      </button>
                    )}
                  </>
                )}

                {hiringLead === lead.id && (
                  <div className="flex gap-2 w-full">
                    <input
                      type="date"
                      value={hireDateInput}
                      onChange={(e) => setHireDateInput(e.target.value)}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
                    />
                    <button
                      onClick={() => reportHire(lead)}
                      disabled={loading}
                      className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-lg transition disabled:opacity-50"
                    >
                      Submit $500
                    </button>
                    <button
                      onClick={() => {
                        setHiringLead(null);
                        setHireDateInput('');
                      }}
                      className="bg-gray-400 hover:bg-gray-500 text-white font-bold py-2 px-4 rounded-lg transition"
                    >
                      Cancel
                    </button>
                  </div>
                )}

                {lead.unlock_status === 'hired' && (
                  <span className="bg-yellow-100 text-yellow-800 px-3 py-2 rounded-lg font-semibold">
                    ✓ Hire Reported
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center gap-2 mt-8">
            <button
              onClick={() => fetchLeads(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition"
            >
              Previous
            </button>

            {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                onClick={() => fetchLeads(page)}
                className={`px-4 py-2 rounded-lg transition ${
                  currentPage === page
                    ? 'bg-blue-600 text-white'
                    : 'border border-gray-300 hover:bg-gray-100'
                }`}
              >
                {page}
              </button>
            ))}

            <button
              onClick={() => fetchLeads(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Resume Modal */}
      {showResumeModal && selectedLead && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-96 overflow-auto">
            <div className="flex justify-between items-center p-6 border-b">
              <h2 className="text-xl font-bold text-gray-800">{selectedLead.job_title}</h2>
              <button
                onClick={() => setShowResumeModal(false)}
                className="text-gray-500 hover:text-gray-700 text-2xl"
              >
                ✕
              </button>
            </div>
            <div className="p-6 whitespace-pre-wrap text-gray-700 font-mono text-sm">
              {resumeLoading ? 'Loading resume...' : fullResume}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

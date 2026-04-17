/**
 * UserDashboard.tsx
 * 
 * User-facing dashboard showing ATS score history chart,
 * summary cards, and the latest keyword heatmap.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { BarChart3, TrendingUp, Target, Activity, ArrowLeft } from 'lucide-react';

interface ScoreHistoryItem {
  session_id: string;
  score: number;
  date: string;
}

interface ScoreHistoryResponse {
  history: ScoreHistoryItem[];
  total_scans: number;
  average_score: number;
  best_score: number;
  latest_score: number;
}

const API_BASE = "";

async function getAuthToken(): Promise<string | null> {
  try {
    const { getSupabaseClient } = await import("../lib/supabase");
    const supabase = getSupabaseClient();
    if (supabase?.auth) {
      const { data } = await supabase.auth.getSession();
      const token = data?.session?.access_token;
      if (token) return token;
    }
  } catch {}
  return localStorage.getItem("auth_token") || localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

export const UserDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<ScoreHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastHeatmapPath = localStorage.getItem('last_heatmap_path');

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const token = await getAuthToken();
        if (!token) {
          setError('Please log in to view your dashboard.');
          setLoading(false);
          return;
        }

        const res = await fetch(`${API_BASE}/api/me/score-history`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });

        if (!res.ok) {
          if (res.status === 401) {
            setError('Session expired. Please log in again.');
          } else {
            setError('Failed to load score history.');
          }
          setLoading(false);
          return;
        }

        const json: ScoreHistoryResponse = await res.json();
        setData(json);
      } catch (err) {
        setError('Failed to connect to server.');
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  const chartData = (data?.history || []).map((item) => ({
    date: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    score: item.score,
  }));

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-emerald-400';
    if (score >= 60) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Header */}
      <header className="border-b border-slate-800/50 bg-slate-900/80 backdrop-blur-xl sticky top-0 z-30">
        <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={18} />
              <span className="text-sm">Back to Scanner</span>
            </button>
            <h1 className="text-xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
              My Dashboard
            </h1>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 space-y-8">
        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-center">
            <p className="text-red-400">{error}</p>
            <button
              onClick={() => navigate('/')}
              className="mt-4 px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 transition-colors"
            >
              Go Back
            </button>
          </div>
        )}

        {/* Dashboard Content */}
        {data && !loading && (
          <>
            {/* Summary Cards */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryCard
                icon={<BarChart3 className="text-emerald-400" size={20} />}
                label="Total Scans"
                value={data.total_scans.toString()}
              />
              <SummaryCard
                icon={<TrendingUp className="text-cyan-400" size={20} />}
                label="Average Score"
                value={`${data.average_score}%`}
                valueClass={getScoreColor(data.average_score)}
              />
              <SummaryCard
                icon={<Target className="text-amber-400" size={20} />}
                label="Best Score"
                value={`${data.best_score}%`}
                valueClass={getScoreColor(data.best_score)}
              />
              <SummaryCard
                icon={<Activity className="text-purple-400" size={20} />}
                label="Latest Score"
                value={`${data.latest_score}%`}
                valueClass={getScoreColor(data.latest_score)}
              />
            </div>

            {/* Score History Chart */}
            {chartData.length > 1 ? (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 backdrop-blur-sm p-6">
                <h2 className="text-lg font-semibold text-white mb-6">ATS Score Over Time</h2>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
                      <YAxis domain={[0, 100]} stroke="#94a3b8" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1e293b',
                          border: '1px solid #475569',
                          borderRadius: '8px',
                          color: '#e2e8f0',
                        }}
                        formatter={(value) => [`${value}%`, 'ATS Score']}
                      />
                      <Area
                        type="monotone"
                        dataKey="score"
                        stroke="#10b981"
                        strokeWidth={2}
                        fill="url(#scoreGradient)"
                        dot={{ fill: '#10b981', strokeWidth: 2, r: 4 }}
                        activeDot={{ r: 6, fill: '#34d399' }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : chartData.length === 1 ? (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 backdrop-blur-sm p-6 text-center">
                <h2 className="text-lg font-semibold text-white mb-2">ATS Score Over Time</h2>
                <p className="text-slate-400 text-sm">Complete more scans to see your score trend chart. You have 1 scan so far.</p>
                <div className="mt-4">
                  <span className={`text-4xl font-bold ${getScoreColor(chartData[0].score)}`}>{chartData[0].score}%</span>
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 backdrop-blur-sm p-6 text-center">
                <h2 className="text-lg font-semibold text-white mb-2">ATS Score Over Time</h2>
                <p className="text-slate-400 text-sm mb-4">No scans yet. Upload your resume and a job description to get started.</p>
                <button
                  onClick={() => navigate('/')}
                  className="px-6 py-2 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white rounded-lg font-semibold hover:shadow-lg transition-all"
                >
                  Start Your First Scan
                </button>
              </div>
            )}

            {/* Keyword Heatmap */}
            {lastHeatmapPath && (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 backdrop-blur-sm p-6">
                <h2 className="text-lg font-semibold text-white mb-4">Latest Keyword Heatmap</h2>
                <img
                  src={`${API_BASE}${lastHeatmapPath}`}
                  alt="Keyword heatmap"
                  className="w-full max-w-2xl mx-auto rounded-lg"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              </div>
            )}
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/50 bg-gradient-to-b from-slate-900/50 to-slate-950 mt-16 py-8">
        <div className="mx-auto max-w-7xl px-4 text-center text-sm text-slate-400">
          <p>IntelliResume AI • Professional ATS Optimization</p>
        </div>
      </footer>
    </div>
  );
};

function SummaryCard({ icon, label, value, valueClass = 'text-white' }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 backdrop-blur-sm p-5">
      <div className="flex items-center gap-3 mb-2">
        {icon}
        <span className="text-sm text-slate-400">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
    </div>
  );
}

export default UserDashboard;

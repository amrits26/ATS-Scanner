// frontend/src/components/AnalyticsDashboard.tsx
import React, { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  Area,
  AreaChart,
} from 'recharts';
import { TrendingUp, Users, AlertCircle, DollarSign, Download } from 'lucide-react';

interface DashboardKPI {
  mrr_total: number;
  active_users: number;
  churn_rate: number;
  ltv: number;
  mrr_change_percent: number;
  user_growth_percent: number;
  churn_improvement_percent: number;
  ltv_improvement_percent: number;
  email_mrr: number;
  coach_mrr: number;
  tailor_mrr: number;
  interview_mrr: number;
  pro_mrr: number;
}

interface ChartDataPoint {
  date: string;
  mrr: number;
}

interface CohortData {
  cohort: string;
  month_1: number;
  month_3: number;
  month_6: number;
}

interface MetricsCardProps {
  title: string;
  value: string;
  change: number;
  icon: React.ReactNode;
  isLoading?: boolean;
}

const MetricsCard: React.FC<MetricsCardProps> = ({ 
  title, 
  value, 
  change, 
  icon,
  isLoading = false
}) => {
  const isPositive = change >= 0;
  
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
        <div className="h-8 bg-gray-200 rounded w-3/4 mb-2"></div>
        <div className="h-4 bg-gray-200 rounded w-1/2"></div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-gray-600 font-medium">{title}</p>
          <p className="text-3xl font-bold text-gray-900 mt-2">{value}</p>
          <p className={`text-sm font-medium mt-2 flex items-center gap-1 ${
            isPositive ? 'text-green-600' : 'text-red-600'
          }`}>
            <span>{isPositive ? '↑' : '↓'}</span>
            {Math.abs(change).toFixed(1)}% vs last period
          </p>
        </div>
        <div className="text-4xl opacity-30 flex-shrink-0">
          {React.cloneElement(icon as React.ReactElement, { size: 32 })}
        </div>
      </div>
    </div>
  );
};

export const AnalyticsDashboard: React.FC = () => {
  const [dateRange, setDateRange] = useState<'7d' | '30d' | '90d'>('30d');
  const [kpis, setKpis] = useState<DashboardKPI | null>(null);
  const [mrrTrend, setMrrTrend] = useState<ChartDataPoint[]>([]);
  const [cohorts, setCohorts] = useState<CohortData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // Fetch KPIs
        const kpiRes = await fetch(`/api/analytics/dashboard?range=${dateRange}`);
        if (!kpiRes.ok) throw new Error('Failed to fetch KPIs');
        const kpiData = await kpiRes.json();
        setKpis(kpiData.data);

        // Fetch MRR trend (6 months)
        const trendRes = await fetch('/api/analytics/mrr');
        if (trendRes.ok) {
          const trendData = await trendRes.json();
          setMrrTrend(trendData.data || []);
        }

        // Fetch cohort data
        const cohortRes = await fetch('/api/analytics/cohorts');
        if (cohortRes.ok) {
          const cohortData = await cohortRes.json();
          setCohorts(cohortData.data || []);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };

    fetchDashboard();
  }, [dateRange]);

  if (error) {
    return (
      <div className="max-w-7xl mx-auto p-6">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          Error: {error}
        </div>
      </div>
    );
  }

  const mrrBreakdown = kpis ? [
    { name: 'Email', value: kpis.email_mrr, color: '#3B82F6' },
    { name: 'Coach', value: kpis.coach_mrr, color: '#8B5CF6' },
    { name: 'Tailor', value: kpis.tailor_mrr, color: '#EC4899' },
    { name: 'Interview', value: kpis.interview_mrr, color: '#F97316' },
    { name: 'Pro', value: kpis.pro_mrr, color: '#10B981' },
  ] : [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="max-w-7xl mx-auto p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900">Analytics Dashboard</h1>
            <p className="text-gray-600 mt-1">Real-time metrics & revenue tracking</p>
          </div>
          <div className="flex gap-2">
            {(['7d', '30d', '90d'] as const).map(range => (
              <button
                key={range}
                onClick={() => setDateRange(range)}
                className={`px-4 py-2 rounded-lg font-medium transition-all transform hover:scale-105 ${
                  dateRange === range
                    ? 'bg-blue-600 text-white shadow-lg'
                    : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
                }`}
              >
                {range === '7d' ? 'Last 7 Days' : range === '30d' ? 'Last 30 Days' : 'Last 90 Days'}
              </button>
            ))}
            <button className="ml-4 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 flex items-center gap-2 font-medium">
              <Download size={18} />
              Export
            </button>
          </div>
        </div>

        {/* KPI Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricsCard
            title="Monthly Recurring Revenue"
            value={kpis ? `$${Math.floor(kpis.mrr_total).toLocaleString()}` : '-'}
            change={kpis?.mrr_change_percent || 0}
            icon={<DollarSign className="text-blue-600" />}
            isLoading={isLoading}
          />
          <MetricsCard
            title="Active Users"
            value={kpis ? kpis.active_users.toLocaleString() : '-'}
            change={kpis?.user_growth_percent || 0}
            icon={<Users className="text-purple-600" />}
            isLoading={isLoading}
          />
          <MetricsCard
            title="Churn Rate"
            value={kpis ? `${(kpis.churn_rate * 100).toFixed(2)}%` : '-'}
            change={kpis ? -kpis.churn_improvement_percent : 0}
            icon={<AlertCircle className="text-red-600" />}
            isLoading={isLoading}
          />
          <MetricsCard
            title="Customer LTV"
            value={kpis ? `$${Math.floor(kpis.ltv).toLocaleString()}` : '-'}
            change={kpis?.ltv_improvement_percent || 0}
            icon={<TrendingUp className="text-green-600" />}
            isLoading={isLoading}
          />
        </div>

        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* MRR Trend Chart */}
          <div className="bg-white rounded-lg shadow-lg p-6 hover:shadow-xl transition-shadow">
            <h3 className="text-lg font-bold text-gray-900 mb-4">MRR Trend (6 Months)</h3>
            {mrrTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={mrrTrend}>
                  <defs>
                    <linearGradient id="colorMrr" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#3B82F6" stopOpacity={0.1}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip 
                    formatter={(value) => `$${Number(value).toLocaleString()}`}
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #ccc' }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="mrr" 
                    stroke="#3B82F6" 
                    fillOpacity={1} 
                    fill="url(#colorMrr)" 
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-500">
                No data available
              </div>
            )}
          </div>

          {/* Revenue Breakdown Pie Chart */}
          <div className="bg-white rounded-lg shadow-lg p-6 hover:shadow-xl transition-shadow">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Revenue Breakdown</h3>
            {mrrBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={mrrBreakdown}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name}: $${value}`}
                    outerRadius={90}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {mrrBreakdown.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `$${Number(value).toLocaleString()}`} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-500">
                No breakdown available
              </div>
            )}
          </div>
        </div>

        {/* Cohort Retention Table */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h3 className="text-lg font-bold text-gray-900 mb-4">Cohort Retention (% Retained)</h3>
          {cohorts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b-2 border-gray-200">
                    <th className="text-left py-3 px-4 font-semibold text-gray-700">Signup Cohort</th>
                    <th className="text-center py-3 px-4 font-semibold text-gray-700">Month 1</th>
                    <th className="text-center py-3 px-4 font-semibold text-gray-700">Month 3</th>
                    <th className="text-center py-3 px-4 font-semibold text-gray-700">Month 6</th>
                  </tr>
                </thead>
                <tbody>
                  {cohorts.map((cohort, i) => (
                    <tr key={i} className="border-b border-gray-100 hover:bg-gray-50 transition">
                      <td className="py-3 px-4 font-medium text-gray-900">{cohort.cohort}</td>
                      <td className="py-3 px-4 text-center">
                        <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
                          {cohort.month_1}%
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm font-medium">
                          {cohort.month_3}%
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
                          {cohort.month_6}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="h-40 flex items-center justify-center text-gray-500">
              No cohort data available
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

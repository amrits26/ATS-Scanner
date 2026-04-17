/**
 * JobSearchWidget – Multi-source job search component.
 *
 * Lets users search LinkedIn / Indeed / Google Jobs / Glassdoor
 * and analyze any result with the ATS scanner.
 */

import React, { useState } from 'react';

interface SearchParams {
  keywords: string;
  location: string;
  source: string;
  daysOld: number;
  remoteOnly: boolean;
  jobType: string;
}

interface ScrapedJob {
  id: string;
  source: string;
  title: string;
  company: string;
  location: string | null;
  description: string;
  posted_date: string | null;
  url: string | null;
  required_skills: { skills?: string[]; soft_skills?: string[] } | null;
}

interface SearchResult {
  run_id: string;
  total_found: number;
  new_jobs: number;
  jobs: ScrapedJob[];
}

export function JobSearchWidget() {
  const [params, setParams] = useState<SearchParams>({
    keywords: '',
    location: '',
    source: 'linkedin',
    daysOld: 7,
    remoteOnly: false,
    jobType: '',
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const getToken = () => localStorage.getItem('access_token') || '';

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch('/api/scraping/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          keywords: params.keywords,
          location: params.location,
          source: params.source,
          max_results: 50,
          days_old: params.daysOld,
          job_type: params.jobType || undefined,
          remote_only: params.remoteOnly,
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }

      setResult(await response.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const analyzeWithATS = (job: ScrapedJob) => {
    window.location.href = `/scanner?jobId=${job.id}&source=scraped`;
  };

  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      <h2 className="text-2xl font-bold mb-4">Find Jobs</h2>

      <form onSubmit={handleSearch} className="space-y-4">
        {/* Row 1: Keywords + Location */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Keywords</label>
            <input
              type="text"
              value={params.keywords}
              onChange={(e) => setParams({ ...params, keywords: e.target.value })}
              placeholder="Job title, skills, or company"
              className="w-full p-2 border rounded-lg"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Location</label>
            <input
              type="text"
              value={params.location}
              onChange={(e) => setParams({ ...params, location: e.target.value })}
              placeholder="City, state, or remote"
              className="w-full p-2 border rounded-lg"
            />
          </div>
        </div>

        {/* Row 2: Filters */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Source</label>
            <select
              aria-label="Job source"
              value={params.source}
              onChange={(e) => setParams({ ...params, source: e.target.value })}
              className="w-full p-2 border rounded-lg"
            >
              <option value="linkedin">LinkedIn</option>
              <option value="indeed">Indeed</option>
              <option value="google_jobs">Google Jobs</option>
              <option value="glassdoor">Glassdoor</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Posted Within</label>
            <select
              aria-label="Posted within"
              value={params.daysOld}
              onChange={(e) => setParams({ ...params, daysOld: Number(e.target.value) })}
              className="w-full p-2 border rounded-lg"
            >
              <option value={1}>24 hours</option>
              <option value={3}>3 days</option>
              <option value={7}>1 week</option>
              <option value={30}>1 month</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Job Type</label>
            <select
              aria-label="Job type"
              value={params.jobType}
              onChange={(e) => setParams({ ...params, jobType: e.target.value })}
              className="w-full p-2 border rounded-lg"
            >
              <option value="">Any</option>
              <option value="full-time">Full-time</option>
              <option value="part-time">Part-time</option>
              <option value="contract">Contract</option>
              <option value="internship">Internship</option>
            </select>
          </div>
          <div className="flex items-end">
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={params.remoteOnly}
                onChange={(e) => setParams({ ...params, remoteOnly: e.target.checked })}
                className="mr-2"
              />
              Remote Only
            </label>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Searching...' : 'Search Jobs'}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-lg">{error}</div>
      )}

      {/* Results */}
      {result && (
        <div className="mt-6">
          <h3 className="text-lg font-semibold mb-3">
            Found {result.total_found} jobs ({result.new_jobs} new)
          </h3>

          <div className="space-y-3 max-h-[32rem] overflow-y-auto">
            {result.jobs.map((job) => (
              <div
                key={job.id}
                className="border rounded-lg p-4 hover:bg-gray-50 cursor-pointer"
                onClick={() => setExpandedId(expandedId === job.id ? null : job.id)}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-medium">{job.title}</h4>
                    <p className="text-gray-600">{job.company}</p>
                    {job.location && <p className="text-sm text-gray-500">{job.location}</p>}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); analyzeWithATS(job); }}
                      className="text-sm px-3 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200"
                    >
                      Analyze with ATS
                    </button>
                    {job.url && (
                      <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-sm px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 inline-flex items-center"
                      >
                        Open &#8599;
                      </a>
                    )}
                  </div>
                </div>

                {expandedId === job.id && (
                  <div className="mt-4 pt-4 border-t">
                    {job.required_skills?.skills && job.required_skills.skills.length > 0 && (
                      <>
                        <h5 className="font-medium mb-2">Required Skills</h5>
                        <div className="flex flex-wrap gap-2 mb-4">
                          {job.required_skills.skills.map((skill) => (
                            <span key={skill} className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-sm">
                              {skill}
                            </span>
                          ))}
                        </div>
                      </>
                    )}
                    <h5 className="font-medium mb-2">Description Preview</h5>
                    <p className="text-sm text-gray-700 line-clamp-3">{job.description}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

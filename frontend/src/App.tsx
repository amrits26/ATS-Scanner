import { useCallback, useState } from "react";
import type { ComprehensiveAnalysisResult } from "./types";
import { ResumeComparison } from "./ResomeComparison";

const API_BASE = "";

// Reusable score card component
function ScoreCard({ label, score, icon }: { label: string; score: number; icon: string }) {
  const getColor = (s: number) => {
    if (s >= 75) return "text-emerald-400";
    if (s >= 50) return "text-amber-400";
    return "text-red-400";
  };
  
  const getBgColor = (s: number) => {
    if (s >= 75) return "glass-card-emerald";
    if (s >= 50) return "bg-amber-900/20 border-amber-700/40";
    return "bg-red-900/20 border-red-700/40";
  };

  return (
    <div className={`rounded-xl p-4 border backdrop-blur-xl transition-all hover:shadow-lg hover:shadow-emerald-500/10 ${getBgColor(score)}`}>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wide">{label}</div>
          <div className={`text-3xl font-bold ${getColor(score)}`}>{Math.round(score)}</div>
        </div>
        <div className="text-4xl opacity-75">{icon}</div>
      </div>
    </div>
  );
}

// Tag component for keywords
function Tag({ text, variant = "default" }: { text: string; variant?: "success" | "warning" | "default" }) {
  const baseClass = "inline-block px-2.5 py-1 text-xs rounded-full whitespace-nowrap";
  const variantClass = {
    success: "bg-emerald-500/20 text-emerald-300",
    warning: "bg-amber-500/20 text-amber-300",
    default: "bg-slate-700/50 text-slate-300",
  }[variant];
  
  return <span className={`${baseClass} ${variantClass}`}>{text}</span>;
}

function App() {
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComprehensiveAnalysisResult | null>(null);
  const [activeTab, setActiveTab] = useState<"dashboard" | "optimize" | "skills" | "quality" | "keywords">("dashboard");

  const [resumeDrag, setResumeDrag] = useState(false);
  const [jdDrag, setJdDrag] = useState(false);

  const handleResumeDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setResumeDrag(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.name.toLowerCase().endsWith(".pdf") || f.name.toLowerCase().endsWith(".docx"))) {
      setResumeFile(f);
      setError(null);
    }
  }, []);

  const handleJdDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setJdDrag(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.name.toLowerCase().endsWith(".pdf") || f.name.toLowerCase().endsWith(".docx") || f.name.toLowerCase().endsWith(".txt"))) {
      setJdFile(f);
      setError(null);
    }
  }, []);

  const analyze = async () => {
    if (!resumeFile) {
      setError("Please upload your resume (PDF or DOCX).");
      return;
    }
    if (!jdText.trim() && !jdFile) {
      setError("Please provide a job description.");
      return;
    }
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("resume", resumeFile);
      if (jdFile) form.append("job_description", jdFile);
      if (jdText.trim()) form.append("jd_text", jdText.trim());
      
      const res = await fetch(`${API_BASE}/api/analyze/comprehensive`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText || "Analysis failed.");
      }
      const data: ComprehensiveAnalysisResult = await res.json();
      setResult(data);
      setActiveTab("dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const downloadDocx = async () => {
    if (!result?.optimized_resume) return;
    try {
      const form = new FormData();
      form.append("optimized_resume", result.optimized_resume);
      const res = await fetch(`${API_BASE}/api/download-docx`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "IntelliResume_Optimized.docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Failed to download DOCX.");
    }
  };

  const tabs = [
    { id: "dashboard" as const, label: "📊 Dashboard" },
    { id: "optimize" as const, label: "✨ Optimized Resume" },
    { id: "skills" as const, label: "🎯 Skill Gap" },
    { id: "quality" as const, label: "⭐ Quality Score" },
    { id: "keywords" as const, label: "🔥 Keywords" },
  ];

  const getScoreColor = (score: number) => {
    if (score >= 75) return "text-emerald-500";
    if (score >= 50) return "text-amber-500";
    return "text-red-500";
  };

  const getScoreBg = (score: number) => {
    if (score >= 75) return "bg-emerald-500/10 border-emerald-500/30";
    if (score >= 50) return "bg-amber-500/10 border-amber-500/30";
    return "bg-red-500/10 border-red-500/30";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100">
      {/* Animated background gradient (optional subtle effect) */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950" />
        <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/5 rounded-full mix-blend-screen filter blur-3xl" />
        <div className="absolute -bottom-10 -left-10 w-80 h-80 bg-cyan-500/5 rounded-full mix-blend-screen filter blur-3xl" />
      </div>
      
      {/* Header */}
      <header className="border-b border-slate-800/50 bg-gradient-to-b from-slate-900/80 to-slate-900/40 backdrop-blur-xl sticky top-0 z-40">
        <div className="mx-auto max-w-7xl px-4 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight gradient-text">
                IntelliResume AI
              </h1>
              <p className="mt-1 text-sm text-slate-400">Professional ATS Optimization & Resume Analysis</p>
            </div>
            <div className="text-4xl">📄✨</div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        {/* Upload Section */}
        {!result && (
          <section className="mb-8">
            <div className="glass-card p-8">
              <h2 className="mb-6 text-xl font-semibold text-white">Start Your Analysis</h2>
              <div className="grid gap-6 sm:grid-cols-2 mb-6">
                <div>
                  <label className="mb-3 block text-sm font-medium text-slate-300">Resume (PDF or DOCX) *</label>
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setResumeDrag(true);
                    }}
                    onDragLeave={() => setResumeDrag(false)}
                    onDrop={handleResumeDrop}
                    className={`flex min-h-[140px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 transition-all ${
                      resumeDrag
                        ? "border-emerald-500 bg-emerald-500/10"
                        : "border-slate-600 hover:border-slate-500 hover:bg-slate-700/20"
                    }`}
                    onClick={() => document.getElementById("resume-input")?.click()}
                  >
                    <input
                      id="resume-input"
                      type="file"
                      accept=".pdf,.docx"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) setResumeFile(f);
                      }}
                    />
                    {resumeFile ? (
                      <div className="text-center">
                        <div className="text-2xl mb-2">✓</div>
                        <span className="text-sm text-emerald-400 font-medium">{resumeFile.name}</span>
                      </div>
                    ) : (
                      <div className="text-center">
                        <div className="text-2xl mb-2">📄</div>
                        <span className="text-sm text-slate-400">Drop file or click to upload</span>
                      </div>
                    )}
                  </div>
                </div>
                <div>
                  <label className="mb-3 block text-sm font-medium text-slate-300">Job Description *</label>
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setJdDrag(true);
                    }}
                    onDragLeave={() => setJdDrag(false)}
                    onDrop={handleJdDrop}
                    className={`flex min-h-[140px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 transition-all ${
                      jdDrag
                        ? "border-emerald-500 bg-emerald-500/10"
                        : "border-slate-600 hover:border-slate-500 hover:bg-slate-700/20"
                    }`}
                    onClick={() => document.getElementById("jd-input")?.click()}
                  >
                    <input
                      id="jd-input"
                      type="file"
                      accept=".pdf,.docx,.txt"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) setJdFile(f);
                      }}
                    />
                    {jdFile || jdText.trim() ? (
                      <div className="text-center">
                        <div className="text-2xl mb-2">✓</div>
                        <span className="text-sm text-emerald-400 font-medium">
                          {jdFile?.name || "Job Description Added"}
                        </span>
                      </div>
                    ) : (
                      <div className="text-center">
                        <div className="text-2xl mb-2">📋</div>
                        <span className="text-sm text-slate-400">Drop file or paste below</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="mb-6">
                <label className="mb-3 block text-sm font-medium text-slate-300">Or paste job description text</label>
                <textarea
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder="Paste the job description here..."
                  className="w-full rounded-lg border border-slate-600 bg-slate-800/50 px-4 py-3 text-sm text-slate-200 placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 transition-colors"
                  rows={5}
                />
              </div>
              <div className="flex items-center gap-4">
                <button
                  onClick={analyze}
                  disabled={loading}
                  className="rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 px-7 py-3 font-semibold text-white transition-all hover:shadow-lg hover:shadow-emerald-500/20 disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {loading ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Analyzing...
                    </>
                  ) : (
                    <>🚀 Analyze Now</>
                  )}
                </button>
                {error && <div className="text-sm text-red-400 bg-red-500/10 px-4 py-2 rounded-lg border border-red-500/20">{error}</div>}
              </div>
            </div>
          </section>
        )}

        {/* Results Section */}
        {result && (
          <section className="space-y-8">
            {/* Top Summary */}
            <div className="glass-card p-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-white">Analysis Results</h2>
                <button
                  onClick={() => {
                    setResult(null);
                    setResumeFile(null);
                    setJdFile(null);
                    setJdText("");
                  }}
                  className="px-4 py-2 rounded-lg bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 transition-colors text-sm border border-slate-600/50"
                >
                  ← New Analysis
                </button>
              </div>

              <div className="grid gap-4 sm:grid-cols-5 mb-6">
                <ScoreCard label="ATS Score" score={result.ats_score.final_ats_score} icon="📊" />
                <ScoreCard label="Skill Gap" score={result.skill_gap.gap_score} icon="🎯" />
                <ScoreCard label="Quality" score={result.resume_quality.overall_score} icon="⭐" />
                <ScoreCard label="Readability" score={result.resume_quality.readability_score} icon="📖" />
                <ScoreCard label="Keywords" score={result.resume_quality.keyword_density_score} icon="🔑" />
              </div>

              <button
                onClick={downloadDocx}
                className="w-full rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 px-6 py-3 font-semibold text-white hover:shadow-lg hover:shadow-emerald-500/20 transition-all mb-6"
              >
                ⬇️ Download Optimized Resume (DOCX)
              </button>

              {/* Tab Navigation */}
              <div className="flex gap-2 border-b border-slate-700/50 overflow-x-auto pb-0 -mx-8 px-8 sticky bg-slate-900/20 backdrop-blur-sm">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-all border-b-2 ${
                      activeTab === tab.id
                        ? "border-emerald-500 text-emerald-400 bg-emerald-500/10"
                        : "border-transparent text-slate-400 hover:text-slate-300 hover:bg-slate-700/20"
                    } rounded-t-lg`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Dashboard Tab */}
            {activeTab === "dashboard" && (
              <div className="space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  {result.chart_paths.keyword_coverage && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Keyword Coverage</h3>
                      <img src={`${API_BASE}${result.chart_paths.keyword_coverage}`} alt="Keyword coverage" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result.chart_paths.match_pie && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Match Ratio</h3>
                      <img src={`${API_BASE}${result.chart_paths.match_pie}`} alt="Match vs missing" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result.chart_paths.keyword_heatmap && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Keyword Heatmap</h3>
                      <img src={`${API_BASE}${result.chart_paths.keyword_heatmap}`} alt="Keyword heatmap" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result.chart_paths.similarity_gauge && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">ATS Score Gauge</h3>
                      <img src={`${API_BASE}${result.chart_paths.similarity_gauge}`} alt="ATS score gauge" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result.chart_paths.skill_gap && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Skill Gap</h3>
                      <img src={`${API_BASE}${result.chart_paths.skill_gap}`} alt="Skill gap" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result.chart_paths.quality_breakdown && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Quality Breakdown</h3>
                      <img src={`${API_BASE}${result.chart_paths.quality_breakdown}`} alt="Quality breakdown" className="w-full rounded-lg" />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Optimized Resume Tab */}
            {activeTab === "optimize" && (
              <div className="glass-card p-8">
                <div className="mb-6">
                  <h2 className="text-2xl font-bold text-white mb-2">Resume Optimization</h2>
                  <p className="text-sm text-slate-400">Compare your original resume with the AI-optimized version. Changes are highlighted for easy review.</p>
                </div>
                <ResumeComparison 
                  original={result.original_resume} 
                  optimized={result.optimized_resume} 
                />
                <div className="mt-6 flex gap-3">
                  <button
                    onClick={downloadDocx}
                    className="rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 px-6 py-2.5 font-semibold text-white transition-all hover:shadow-lg hover:shadow-emerald-500/20 flex items-center gap-2"
                  >
                    📥 Download as DOCX
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const form = new FormData();
                        form.append("optimized_resume", result.optimized_resume);
                        const res = await fetch(`${API_BASE}/api/preview-docx`, {
                          method: "POST",
                          body: form,
                        });
                        if (!res.ok) throw new Error("Preview failed");
                        const data = await res.json();
                        // Open preview in new window
                        const preview = window.open();
                        if (preview) {
                          preview.document.write(data.html);
                          preview.document.close();
                        }
                      } catch (e) {
                        setError("Failed to preview DOCX");
                      }
                    }}
                    className="rounded-lg bg-slate-700 px-6 py-2.5 font-semibold text-slate-200 transition-all hover:bg-slate-600 flex items-center gap-2"
                  >
                    👁️ Preview
                  </button>
                </div>
              </div>
            )}

            {/* Skills Tab */}
            {activeTab === "skills" && (
              <div className="space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  <div className="glass-card p-6">
                    <h3 className="mb-4 font-semibold text-emerald-400 flex items-center gap-2">✓ Matched Skills ({result.skill_gap.match_count})</h3>
                    <div className="flex flex-wrap gap-2">
                      {result.skill_gap.matched_skills.length > 0 ? (
                        result.skill_gap.matched_skills.slice(0, 20).map((skill) => (
                          <Tag key={skill} text={skill} variant="success" />
                        ))
                      ) : (
                        <p className="text-sm text-slate-500">No matched skills</p>
                      )}
                    </div>
                  </div>
                  <div className="glass-card p-6">
                    <h3 className="mb-4 font-semibold text-red-400 flex items-center gap-2">✗ Missing Skills ({result.skill_gap.missing_skills.length})</h3>
                    <div className="flex flex-wrap gap-2">
                      {result.skill_gap.missing_skills.length > 0 ? (
                        result.skill_gap.missing_skills.slice(0, 20).map((skill) => (
                          <Tag key={skill} text={skill} variant="warning" />
                        ))
                      ) : (
                        <p className="text-sm text-slate-500">Great! No missing critical skills</p>
                      )}
                    </div>
                  </div>
                </div>
                <div className={`glass-card p-6 ${getScoreBg(result.skill_gap.gap_score)}`}>
                  <h3 className={`text-lg font-semibold mb-2 ${getScoreColor(result.skill_gap.gap_score)}`}>Skill Gap Score: {result.skill_gap.gap_score.toFixed(1)}%</h3>
                  <p className="text-sm text-slate-300">
                    You have matched {result.skill_gap.match_count} out of {result.skill_gap.total_required} required skills.
                  </p>
                </div>
              </div>
            )}

            {/* Quality Tab */}
            {activeTab === "quality" && (
              <div className="space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  <ScoreCard label="Overall Quality" score={result.resume_quality.overall_score} icon="⭐" />
                  <ScoreCard label="Readability" score={result.resume_quality.readability_score} icon="📖" />
                  <ScoreCard label="Formatting" score={result.resume_quality.formatting_score} icon="🎨" />
                  <ScoreCard label="Content" score={result.resume_quality.content_score} icon="✏️" />
                </div>
                <div className="glass-card p-6">
                  <h3 className="mb-4 font-semibold text-white">Feedback & Recommendations</h3>
                  <ul className="space-y-3">
                    {result.resume_quality.feedback.map((item, i) => (
                      <li key={i} className="flex gap-3 text-sm text-slate-300">
                        <span className="text-emerald-400">•</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Keywords Tab */}
            {activeTab === "keywords" && (
              <div className="space-y-6">
                <div className="glass-card p-6">
                  <h3 className="mb-4 font-semibold text-white">Keyword Analysis</h3>
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Missing Keywords ({result.ats_score.missing_keywords.length})</h4>
                      <div className="flex flex-wrap gap-2">
                        {result.ats_score.missing_keywords.slice(0, 30).map((k) => (
                          <Tag key={k} text={k} variant="warning" />
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Recommended to Add</h4>
                      <div className="flex flex-wrap gap-2">
                        {result.ats_score.recommended_keywords_to_add.slice(0, 20).map((k) => (
                          <Tag key={k} text={k} variant="success" />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="glass-card p-6">
                  <h3 className="mb-4 font-semibold text-white">Top JD Keywords & Tools</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Required Skills</h4>
                      <div className="flex flex-wrap gap-2">
                        {result.jd_analysis.required_skills.slice(0, 15).map((s) => (
                          <Tag key={s} text={s} variant="success" />
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Tools & Technologies</h4>
                      <div className="flex flex-wrap gap-2">
                        {result.jd_analysis.tools.slice(0, 15).map((t) => (
                          <Tag key={t} text={t} />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/50 bg-gradient-to-b from-slate-900/50 to-slate-950 backdrop-blur-xl mt-16 py-8">
        <div className="mx-auto max-w-7xl px-4 text-center text-sm text-slate-400">
          <p>IntelliResume AI • Professional ATS Optimization • Powered by OpenAI</p>
        </div>
      </footer>
    </div>
  );
}

export default App;

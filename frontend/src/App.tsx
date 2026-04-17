import { useCallback, useState, useEffect } from "react";
import { Target, BarChart3, Zap, Activity, ShieldCheck, TrendingUp, AlertCircle, CheckCircle2, Lock, ExternalLink } from 'lucide-react';
import type { ComprehensiveAnalysisResult, UserTierEnum } from "./types";
import { ResumeComparison } from "./ResomeComparison";
import { AuthModal } from "./components/AuthModal";
import { UserProfileDropdown } from "./components/UserProfileDropdown";
import { EnhancedLiveKeywordWidget } from "./components/EnhancedLiveKeywordWidget";
import { CredibilityCard } from "./components/CredibilityCard";
import { FeedbackModal } from "./components/FeedbackModal";
import UpgradeModal from "./components/UpgradeModalComponent";
import { TailorRewriteModal } from "./components/TailorRewriteModal";
import { InterviewPrepWidget } from "./components/InterviewPrepWidget";
import { initSupabaseClient } from "./lib/supabase";

const API_BASE = "";

// ============================================================================
// Types & Constants
// ============================================================================

interface AnalysisStatus {
  session_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  result?: ComprehensiveAnalysisResult;
  error_message?: string;
}

interface UserProfile {
  id: string;
  email: string;
  full_name?: string;
  tier: UserTierEnum;
  scans_this_month: number;
  scan_limit: number;
  created_at: string;
}

const POLLING_INTERVAL = 2000; // 2 seconds
const ANALYSIS_STEPS = [
  "Extracting resume...",
  "Analyzing job description...",
  "Optimizing resume...",
  "Computing ATS score...",
  "Analyzing skill gaps...",
  "Scoring quality metrics...",
  "Generating keyword heatmap...",
  "Creating visualizations...",
];

// Helper to get JWT token from Supabase or localStorage
async function getAuthToken(): Promise<string | null> {
  try {
    // Try Supabase client first
    const { getSupabaseClient } = await import("./lib/supabase");
    const supabase = getSupabaseClient();
    
    if (supabase?.auth) {
      const { data } = await supabase.auth.getSession();
      const token = data?.session?.access_token;
      if (token) {
        // Cache in localStorage for fallback
        localStorage.setItem("auth_token", token);
        return token;
      }
    }
    
    // Fallback: check localStorage
    const cachedToken = localStorage.getItem("auth_token");
    if (cachedToken) return cachedToken;

    // No session found
    return null;
  } catch (err) {
    console.warn("Failed to get auth token:", err);
    return localStorage.getItem("auth_token") || null;
  }
}

// Helper to check if user is logged in
async function isLoggedIn(): Promise<boolean> {
  const token = await getAuthToken();
  return !!token;
}

// Helper to make authenticated fetch calls
async function authenticatedFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = await getAuthToken();
  
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  // Only set Content-Type for JSON requests when NOT sending FormData
  // If body is FormData, let the browser set multipart/form-data boundary automatically
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  
  // Merge existing headers if they exist
  if (options.headers && typeof options.headers === 'object' && !(options.headers instanceof Headers)) {
    Object.assign(headers, options.headers as Record<string, string>);
  }
  
  return fetch(url, { ...options, headers });
}

// Track affiliate clicks for analytics
async function trackAffiliateClick(offer: string, score: number) {
  try {
    await fetch('/api/analytics/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event: 'affiliate_click',
        offer: offer,
        score: score,
        page: 'results',
        timestamp: new Date().toISOString()
      })
    }).catch(() => null); // silent fail – don't block user
  } catch (err) {
    // silent fail
  }
}

// ============================================================================
// Reusable Components
// ============================================================================

// Reusable score card component
function ScoreCard({ label, score, icon, locked = false }: { label: string; score: number; icon: string; locked?: boolean }) {
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
    <div className={`rounded-xl p-4 border backdrop-blur-xl transition-all hover:shadow-lg hover:shadow-emerald-500/10 relative ${locked ? "opacity-50 blur-sm" : getBgColor(score)}`}>
      {locked && (
        <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/30 backdrop-blur-sm">
          <span className="text-2xl">🔒</span>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wide">{label}</div>
          <div className={`text-3xl font-bold ${locked ? "text-slate-500" : getColor(score)}`}>{Math.round(score)}</div>
        </div>
        <div className="text-4xl opacity-75">{icon}</div>
      </div>
    </div>
  );
}

// Tag component for keywords
function Tag({ text, variant = "default", locked = false }: { text: string; variant?: "success" | "warning" | "default"; locked?: boolean }) {
  const baseClass = "inline-block px-2.5 py-1 text-xs rounded-full whitespace-nowrap relative group";
  const variantClass = {
    success: "bg-emerald-500/20 text-emerald-300",
    warning: "bg-amber-500/20 text-amber-300",
    default: "bg-slate-700/50 text-slate-300",
  }[variant];
  
  return (
    <span className={`${baseClass} ${locked ? "opacity-40 blur-sm" : variantClass}`}>
      {locked && <span className="absolute inset-0 flex items-center justify-center text-xs">🔒</span>}
      {text}
    </span>
  );
}

// Progress bar component
function ProgressBar({ currentStep, totalSteps, message }: { currentStep: number; totalSteps: number; message: string }) {
  const percentComplete = (currentStep / totalSteps) * 100;
  return (
    <div className="glass-card p-6 mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-medium text-slate-300">{message}</div>
        <div className="text-xs text-slate-400 font-mono">Step {currentStep}/{totalSteps}</div>
      </div>
      <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden border border-slate-600/50">
        <div
          className="h-full bg-gradient-to-r from-emerald-500 to-cyan-500 transition-all duration-500 ease-out"
          style={{ width: `${percentComplete}%` }}
        />
      </div>
    </div>
  );
}

// Paywall overlay for pro-only features
function PaywallOverlay({ onUpgradeClick }: { onUpgradeClick: () => void }) {
  return (
    <div className="absolute inset-0 bg-black/40 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center z-10 group hover:bg-black/50 transition-colors cursor-pointer" onClick={onUpgradeClick}>
      <div className="bg-slate-950/90 border border-slate-700 rounded-lg p-6 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-sm font-semibold text-white mb-2">Pro Feature</div>
        <div className="text-xs text-slate-400 mb-4">Upgrade to Pro to unlock</div>
        <button className="px-4 py-2 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white text-xs font-semibold rounded-lg hover:shadow-lg hover:shadow-emerald-500/20 transition-all">
          Upgrade Now
        </button>
      </div>
    </div>
  );
}

function App() {
  // Auth & User state
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  // File upload state
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");

  // Analysis state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComprehensiveAnalysisResult | null>(null);

  // Polling state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [isManualStart, setIsManualStart] = useState(false); // Track if user explicitly clicked Analyze
  
  // Phase 1 & 3: Real-time keywords and feedback
  const [liveKeywords, setLiveKeywords] = useState<any | null>(null);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

  // UI state
  const [activeTab, setActiveTab] = useState<"dashboard" | "optimize" | "skills" | "quality" | "keywords">("dashboard");
  const [resumeDrag, setResumeDrag] = useState(false);
  const [jdDrag, setJdDrag] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [showTailorModal, setShowTailorModal] = useState(false);

  // ========================================================================
  // Effects
  // ========================================================================

  // Initialize Supabase and load user profile on mount
  useEffect(() => {
    const initAndLoadUser = async () => {
      try {
        // Initialize Supabase client (singleton, safe to call multiple times)
        const supabase = initSupabaseClient();
        
        if (!supabase) {
          console.warn("⚠️ Supabase not initialized - auth will be unavailable");
          setAuthLoading(false);
          return;
        }

        // Set up auth state change listener for session persistence
        const { data: { subscription } } = supabase.auth.onAuthStateChange(
          async (_event: any, session: any) => {
            if (session) {
              localStorage.setItem("auth_token", session.access_token);
              // Fetch user profile when session changes
              try {
                const res = await fetch(`${API_BASE}/api/me`, {
                  headers: {
                    'Authorization': `Bearer ${session.access_token}`,
                    'Content-Type': 'application/json',
                  },
                });
                if (res.ok) {
                  const userData = await res.json();
                  setUser(userData);
                }
              } catch (err) {
                console.error("Error fetching user profile on auth change:", err);
              }
            } else {
              localStorage.removeItem("auth_token");
              setUser(null);
            }
          }
        );

        // Check if already logged in
        const loggedIn = await isLoggedIn();
        if (loggedIn) {
          try {
            const token = await getAuthToken();
            const res = await fetch(`${API_BASE}/api/me`, {
              headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
            });
            if (res.ok) {
              const userData = await res.json();
              setUser(userData);
            }
          } catch (err) {
            console.error("Error fetching user profile:", err);
          }
        }

        setAuthLoading(false);

        return () => {
          subscription?.unsubscribe();
        };
      } catch (err) {
        console.error("Initialization error:", err);
        setAuthLoading(false);
      }
    };

    initAndLoadUser();
  }, []);

  // Session recovery from localStorage with validation
  useEffect(() => {
    const savedSessionId = localStorage.getItem("active_session_id");
    if (savedSessionId && !result) {
      // Restore persisted analysis session from localStorage
      // This allows users to refresh the page and still see their results
      setSessionId(savedSessionId);
      // Defer loading state to allow useEffect dependencies to stabilize
      setTimeout(() => setLoading(true), 0);
    }
  }, [result]);

  // Handle Stripe payment success redirect
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const upgradeSuccess = urlParams.get("upgrade");

    if (upgradeSuccess === "success") {
      console.log("[PAYMENT] User redirected from Stripe checkout - refreshing user tier...");
      
      // Refresh user tier data
      const refreshUserTier = async () => {
        try {
          const token = localStorage.getItem("jwt_token");
          if (!token) {
            console.error("[PAYMENT] No auth token found");
            return;
          }
          const res = await fetch(`${API_BASE}/api/me`, {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          });
          
          if (res.ok) {
            const updatedUser = await res.json();
            setUser(updatedUser);
            console.log("[PAYMENT] User tier updated:", updatedUser.tier);
            
            // Show success message
            setError(null);
          }
        } catch (err) {
          console.error("[PAYMENT] Error refreshing user tier:", err);
        }
      };

      refreshUserTier();

      // Close upgrade modal
      setShowUpgradeModal(false);

      // Clean up URL parameter
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // Debug: Track result changes
  useEffect(() => {
    if (result) {
      console.log("[RESULT] Analysis result received:");
      console.log("  - ATS Score:", result.ats_score?.final_ats_score ?? "undefined");
      console.log("  - Skill Gap Score:", result.skill_gap?.gap_score ?? "undefined");
      console.log("  - Resume Quality:", result.resume_quality?.overall_score ?? "undefined");
      console.log("  - Keyword Heatmap Keywords:", result.keyword_heatmap?.keywords?.length ?? 0, "keywords");
      console.log("  - Chart Paths:", Object.keys(result.chart_paths ?? {}).length, "charts");
      console.log("[RESULT] Full result object:", result);
    }
  }, [result]);

  // Polling effect: poll status every 2 seconds
  // Only poll if user explicitly started an analysis (isManualStart = true)
  useEffect(() => {
    if (!sessionId || !loading || !isManualStart) return;

    let pollAttempts = 0;
    const MAX_POLL_ATTEMPTS = 7200; // 4 hours at 2-second intervals (2 * 60 * 60)
    
    const pollInterval = setInterval(async () => {
      pollAttempts++;
      
      try {
        const res = await authenticatedFetch(`${API_BASE}/api/analysis/${sessionId}/status`);
        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP ${res.status}: ${res.statusText}`);
        }

        const data = (await res.json()) as AnalysisStatus;

        if (data.status === "completed" && data.result) {
          console.log("[DEBUG] Analysis completed. Result keys:", Object.keys(data.result));
          console.log("[DEBUG] Keyword heatmap:", data.result?.keyword_heatmap?.keywords?.slice(0, 10) ?? "MISSING");
          console.log("[DEBUG] Chart paths:", Object.keys(data.result?.chart_paths ?? {}) ?? "MISSING");
          console.log("[DEBUG] ATS Score:", data.result?.ats_score?.final_ats_score ?? "MISSING");
          console.log("[DEBUG] Skill Gap:", data.result?.skill_gap?.gap_score ?? "MISSING");
          setResult(data.result);
          setLoading(false);
          setLiveKeywords(null);  // Clear live keywords
          localStorage.removeItem("active_session_id");
          setCurrentStep(ANALYSIS_STEPS.length);
          
          // Persist resume text for InterviewPrepWidget
          if (data.result?.original_resume) {
            localStorage.setItem('current_resume', data.result.original_resume);
          }
          // Store last heatmap path for dashboard
          if (data.result?.chart_paths?.keyword_heatmap) {
            localStorage.setItem('last_heatmap_path', data.result.chart_paths.keyword_heatmap);
          }
          
          // Phase 3: Show feedback modal on completion
          setTimeout(() => setShowFeedbackModal(true), 1000);
          
          // Show Tailor modal for improvable scores (50-80)
          const score = data.result?.ats_score?.final_ats_score ?? 0;
          if (score >= 50 && score <= 80) {
            setTimeout(() => setShowTailorModal(true), 3000);
          }
        } else if (data.status === "failed") {
          console.error("[DEBUG] Analysis failed:", data.error_message);
          setError(data.error_message || "Analysis failed. Please try again.");
          setLoading(false);
          setLiveKeywords(null);  // Clear live keywords
          localStorage.removeItem("active_session_id");
        } else {
          // Phase 1: Extract live keywords during processing
          if (data.live_keywords) {
            setLiveKeywords(data.live_keywords);
          }
          
          // Update progress based on status or estimate based on time
          const stepMap: Record<string, number> = {
            pending: 0,
            processing: Math.min(currentStep + 1, ANALYSIS_STEPS.length - 2),
            completed: ANALYSIS_STEPS.length,
          };
          setCurrentStep(stepMap[data.status] ?? currentStep);
        }
        
        // Reset attempts counter on successful poll
        pollAttempts = 0;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("Polling error:", errorMsg);
        
        // If polling fails multiple times in a row, log it
        if (pollAttempts > 3) {
          console.error(`Polling failed ${pollAttempts} times consecutively`);
        }
        
        // If we've hit max attempts, stop polling and show error to user
        if (pollAttempts >= MAX_POLL_ATTEMPTS) {
          setError(`Analysis took too long. Last error: ${errorMsg}. Please refresh and try again.`);
          setLoading(false);
          localStorage.removeItem("active_session_id");
          clearInterval(pollInterval);
        }
      }
    }, POLLING_INTERVAL);

    return () => clearInterval(pollInterval);
  }, [sessionId, loading, currentStep, isManualStart]);

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

  // Clear results and reset to clean state
  const clearResults = useCallback(async () => {
    const currentSessionId = sessionId || localStorage.getItem("active_session_id");
    
    // Check if session exists on server; if 404, it's already gone
    if (currentSessionId) {
      try {
        const res = await authenticatedFetch(`${API_BASE}/api/analysis/${currentSessionId}/status`);
        if (res.status === 404) {
          // Session not found on server, clean remove from localStorage
          localStorage.removeItem("active_session_id");
        }
      } catch (err) {
        // Network error or other issue, still clean up locally
        console.warn("Error checking session status during clear:", err);
        localStorage.removeItem("active_session_id");
      }
    }
    
    // Reset all state
    setResult(null);
    setSessionId(null);
    setLoading(false);
    setError(null);
    setCurrentStep(0);
    setIsManualStart(false);
    setResumeFile(null);
    setJdFile(null);
    setJdText("");
    localStorage.removeItem("active_session_id");
    setActiveTab("dashboard");
  }, [sessionId]);

  const analyze = async () => {
    // Check if user is authenticated
    if (!user || !user.id) {
      setError("You must be logged in to analyze. Please ensure you have a valid authentication token. Check browser console for details.");
      return;
    }

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
    setIsManualStart(true); // Mark that user explicitly started this analysis
    setResult(null);
    setCurrentStep(0);

    try {
      const form = new FormData();
      form.append("resume", resumeFile);
      if (jdFile) form.append("job_description", jdFile);
      if (jdText.trim()) form.append("jd_text", jdText.trim());
      // Add user timezone for quiet hours enforcement
      const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      form.append("timezone", userTimezone);

      // Send initial request - expect 202 Accepted
      const res = await authenticatedFetch(`${API_BASE}/api/analyze/comprehensive`, {
        method: "POST",
        body: form,
      });

      if (res.status === 202) {
        // Async job queued
        const data = await res.json();
        console.log("[DEBUG] Analysis queued successfully. Response:", data);
        const newSessionId = data.session_id;
        setSessionId(newSessionId);
        localStorage.setItem("active_session_id", newSessionId);
        // Polling will automatically start via useEffect
      } else if (res.status === 503) {
        throw new Error("Analysis queue is temporarily unavailable (Redis service down). Please try again in a moment.");
      } else if (res.status === 401) {
        throw new Error("Authentication failed. Your token may have expired. Please refresh the page.");
      } else if (res.ok) {
        // Synchronous response (fallback for legacy v1 endpoints)
        const data: ComprehensiveAnalysisResult = await res.json();
        setResult(data);
        setLoading(false);
        setCurrentStep(ANALYSIS_STEPS.length);
        localStorage.removeItem("active_session_id");
        setActiveTab("dashboard");
      } else if (res.status === 402) {
        // Payment required - user hit scan limit
        setLoading(false);
        setShowUpgradeModal(true);
        setError("You've reached your monthly scan limit. Upgrade to Pro for unlimited scans.");
        return;
      } else {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText || "Analysis failed.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setLoading(false);
      setIsManualStart(false); // Reset manual start flag on error
      localStorage.removeItem("active_session_id");
    }
  };

  const downloadDocx = async () => {
    if (!result?.optimized_resume) return;
    
    // Check Pro tier access
    if (user && user.tier !== "pro") {
      setShowUpgradeModal(true);
      return;
    }

    try {
      const form = new FormData();
      form.append("optimized_resume", result.optimized_resume);
      const res = await authenticatedFetch(`${API_BASE}/api/download-docx`, {
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

  const handleLogout = async () => {
    try {
      const { getSupabaseClient } = await import("./lib/supabase");
      const supabase = getSupabaseClient();
      if (supabase?.auth) {
        await supabase.auth.signOut();
      }
      // Comprehensive cleanup on logout
      localStorage.removeItem("auth_token");
      localStorage.removeItem("active_session_id");
      setUser(null);
      setResult(null);
      setSessionId(null);
      setLoading(false);
      setIsManualStart(false);
      setError(null);
      setCurrentStep(0);
    } catch (err) {
      console.error("Logout error:", err);
    }
  };

  const handleAuthSuccess = (profile: UserProfile) => {
    setUser(profile);
    setShowAuthModal(false);
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
            <div className="flex items-center gap-4">
              <div className="text-4xl">📄✨</div>
              <a
                href="/pricing"
                className="px-4 py-2 rounded-lg bg-slate-700/50 hover:bg-slate-600/50 text-slate-200 text-sm font-semibold border border-slate-600/30 transition-all"
              >
                💰 Pricing
              </a>
              <a
                href="/dashboard"
                className="px-4 py-2 rounded-lg bg-slate-700/50 hover:bg-slate-600/50 text-slate-200 text-sm font-semibold border border-slate-600/30 transition-all"
              >
                📊 My Dashboard
              </a>
              <a
                href="/recruiter"
                className="px-4 py-2 rounded-lg bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 text-sm font-semibold border border-purple-500/30 transition-all"
              >
                💼 Recruiter Portal
              </a>
              {user ? (
                <UserProfileDropdown user={user} onLogout={handleLogout} />
              ) : (
                <button
                  onClick={() => setShowAuthModal(true)}
                  className="px-4 py-2 rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 text-white text-sm font-semibold hover:shadow-lg hover:shadow-emerald-500/20 transition-all"
                >
                  Sign In
                </button>
              )}
            </div>
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
                  onClick={() => !user?.id ? setShowAuthModal(true) : analyze()}
                  disabled={loading || authLoading}
                  title={authLoading ? "Loading..." : !user?.id ? "Click to login" : "Start analysis"}
                  className="rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 px-7 py-3 font-semibold text-white transition-all hover:shadow-lg hover:shadow-emerald-500/20 disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {authLoading ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Authenticating...
                    </>
                  ) : loading ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Analyzing...
                    </>
                  ) : !user?.id ? (
                    <>🔐 Log In to Analyze</>
                  ) : (
                    <>🚀 Analyze Now</>
                  )}
                </button>
                {error && <div className="text-sm text-red-400 bg-red-500/10 px-4 py-2 rounded-lg border border-red-500/20 flex-1">{error}</div>}
              </div>
            </div>
          </section>
        )}

        {/* Results Section */}
        {loading && (
          <section className="mb-8">
            <ProgressBar currentStep={currentStep + 1} totalSteps={ANALYSIS_STEPS.length} message={ANALYSIS_STEPS[currentStep] || "Processing..."} />
            
            {/* Phase 1: Real-Time Keyword Widget (Enhanced) */}
            {result?.keyword_heatmap?.keywords && (
              <EnhancedLiveKeywordWidget 
                keywords={result?.keyword_heatmap?.keywords} 
                confidence={result?.ats_score?.confidence_score}
              />
            )}
          </section>
        )}

        {result && (
          <section className="space-y-8">
            {/* Top Summary */}
            <div className="glass-card p-8">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-white">Analysis Results</h2>
                <button
                  onClick={clearResults}
                  className="px-4 py-2 rounded-lg bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 transition-colors text-sm border border-slate-600/50"
                >
                  ← New Analysis
                </button>
              </div>

              <div className="grid gap-4 sm:grid-cols-4 mb-6">
                <ScoreCard label="ATS Score" score={result?.ats_score?.final_ats_score ?? 0} icon="📊" />
                <ScoreCard label="Percentile" score={result?.ats_score?.percentile_rank ?? 0} icon="📈" />
                <ScoreCard label="Skill Gap" score={result?.skill_gap?.gap_score ?? 0} icon="🎯" locked={user?.tier !== "pro"} />
                <ScoreCard label="Quality" score={result?.resume_quality?.overall_score ?? 0} icon="⭐" locked={user?.tier !== "pro"} />
              </div>

              <div className="flex gap-3 mb-6">
                <button
                  onClick={downloadDocx}
                  disabled={user?.tier !== "pro"}
                  title={user?.tier !== "pro" ? "Upgrade to Pro to download" : "Download optimized resume"}
                  className={`flex-1 rounded-lg px-6 py-3 font-semibold transition-all flex items-center justify-center gap-2 ${
                    user?.tier === "pro"
                      ? "bg-gradient-to-r from-emerald-600 to-cyan-600 text-white hover:shadow-lg hover:shadow-emerald-500/20"
                      : "bg-slate-700/50 text-slate-400 cursor-not-allowed opacity-60"
                  }`}
                >
                  ⬇️ Download Optimized Resume (DOCX)
                  {user?.tier !== "pro" && <span className="text-lg">🔒</span>}
                </button>
                {(result?.ats_score?.final_ats_score ?? 0) >= 50 && (result?.ats_score?.final_ats_score ?? 0) <= 80 && (
                  <button
                    onClick={() => setShowTailorModal(true)}
                    className="rounded-lg px-6 py-3 font-semibold transition-all bg-gradient-to-r from-blue-600 to-blue-700 text-white hover:from-blue-700 hover:to-blue-800 hover:shadow-lg hover:shadow-blue-500/20 flex items-center gap-2"
                  >
                    🚀 Tailor for This Job — $29
                  </button>
                )}
                <InterviewPrepWidget />
              </div>

              {/* ============= CREDIBILITY LAYER (Phase 6) ============= */}
              <CredibilityCard atsScoreData={result?.ats_score || {}} />

              {/* ============= AFFILIATE HOOKS ============= */}

              {/* HOOK 1: Low Score → Resume Writing Service */}
              {(result?.ats_score?.final_ats_score ?? 0) < 40 && (
                <div className="bg-red-50 border-l-4 border-red-500 p-4 my-4 rounded-lg">
                  <p className="font-bold text-red-800">⚠️ Your resume needs major improvement.</p>
                  <a
                    href="https://topresume.com/?via=intelliresume-lowscore"
                    target="_blank"
                    rel="sponsored noopener"
                    onClick={() => trackAffiliateClick('TopResume:LowScore', result?.ats_score?.final_ats_score ?? 0)}
                    className="inline-block mt-2 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700 transition-colors font-semibold"
                  >
                    ✍️ Get a professional rewrite (Save 20%)
                  </a>
                </div>
              )}

              {/* HOOK 2: Missing Skills → Course Affiliates */}
              {result?.skill_gap?.missing_skills && result?.skill_gap?.missing_skills.length > 0 && (
                <div className="bg-yellow-50 border-l-4 border-yellow-500 p-4 my-4 rounded-lg">
                  <p className="font-semibold text-yellow-800">📚 Close the skill gap:</p>
                  <ul className="mt-2 space-y-2">
                    {result?.skill_gap?.missing_skills?.slice(0, 3).map((skill: string) => {
                      const courseMap: Record<string, string> = {
                        'python': 'https://coursera.pxf.io/c/3045222/1206682/14726?u=https%3A%2F%2Fcoursera.org%2Flearn%2Fpython-for-everybody',
                        'sql': 'https://udemy.com/sql-for-data-analysis/?couponCode=SKILLS2024',
                        'aws': 'https://click.linksynergy.com/deeplink?id=0vb5Rjx9cJo&mid=39197&murl=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Faws-certified-cloud-practitioner-new%2F',
                        'react': 'https://udemy.com/react-the-complete-guide/?couponCode=SKILLS2024',
                        'javascript': 'https://coursera.pxf.io/c/3045222/1206682/14726?u=https%3A%2F%2Fcoursera.org%2Flearn%2Fjavascript-for-beginners',
                        'default': `https://www.udemy.com/courses/search/?src=sac&q=${encodeURIComponent(skill)}`
                      };
                      const url = courseMap[skill.toLowerCase()] || courseMap.default;
                      return (
                        <li key={skill}>
                          <a
                            href={url}
                            target="_blank"
                            rel="sponsored noopener"
                            onClick={() => trackAffiliateClick(`Course:${skill}`, result?.ats_score?.final_ats_score ?? 0)}
                            className="text-blue-600 hover:underline font-medium"
                          >
                            Learn {skill} → (course recommendation)
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {/* HOOK 3: High Score → LinkedIn Premium */}
              {(result?.ats_score?.final_ats_score ?? 0) >= 80 && (
                <div className="bg-green-50 border-l-4 border-green-500 p-4 my-4 rounded-lg flex justify-between items-center">
                  <div>
                    <p className="font-bold text-green-800">🏆 Top Score! Stand out to recruiters.</p>
                    <p className="text-sm text-green-700">Get LinkedIn Premium to message hiring managers directly.</p>
                  </div>
                  <a
                    href="https://linkedin.com/premium?trk=ats_share"
                    target="_blank"
                    rel="sponsored noopener"
                    onClick={() => trackAffiliateClick('LinkedInPremium', result?.ats_score?.final_ats_score ?? 0)}
                    className="bg-blue-700 text-white px-4 py-2 rounded hover:bg-blue-800 transition-colors font-semibold whitespace-nowrap ml-4"
                  >
                    Try 1 month free
                  </a>
                </div>
              )}

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
                  {result?.chart_paths?.keyword_coverage && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Keyword Coverage</h3>
                      <img src={`${API_BASE}${result.chart_paths.keyword_coverage}`} alt="Keyword coverage" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result?.chart_paths?.match_pie && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Match Ratio</h3>
                      <img src={`${API_BASE}${result.chart_paths.match_pie}`} alt="Match vs missing" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result?.chart_paths?.keyword_heatmap && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Keyword Heatmap</h3>
                      <img src={`${API_BASE}${result.chart_paths.keyword_heatmap}`} alt="Keyword heatmap" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result?.chart_paths?.similarity_gauge && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">ATS Score Gauge</h3>
                      <img src={`${API_BASE}${result.chart_paths.similarity_gauge}`} alt="ATS score gauge" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result?.chart_paths?.skill_gap && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Skill Gap</h3>
                      <img src={`${API_BASE}${result.chart_paths.skill_gap}`} alt="Skill gap" className="w-full rounded-lg" />
                    </div>
                  )}
                  {result?.chart_paths?.quality_breakdown && (
                    <div className="glass-card p-6 overflow-hidden">
                      <h3 className="mb-4 font-semibold text-white">Quality Breakdown</h3>
                      <img src={`${API_BASE}${result.chart_paths.quality_breakdown}`} alt="Quality breakdown" className="w-full rounded-lg" />
                    </div>
                  )}
                </div>

                {/* Missing Keywords Section */}
                {result?.ats_score?.missing_keywords && result.ats_score.missing_keywords.length > 0 && (
                  <div className="glass-card p-6">
                    <h3 className="mb-4 font-semibold text-amber-400 flex items-center gap-2">
                      ⚠️ Missing Keywords ({result.ats_score.missing_keywords.length})
                    </h3>
                    <p className="text-sm text-slate-400 mb-4">These keywords from the job description are missing from your resume. Adding them could significantly improve your ATS score.</p>
                    <div className="flex flex-wrap gap-2">
                      {(user?.tier === "pro" ? result.ats_score.missing_keywords : result.ats_score.missing_keywords.slice(0, 3)).map((keyword) => (
                        <span
                          key={keyword}
                          title="Add this keyword to your resume to improve your ATS score"
                          className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 transition-colors cursor-default"
                        >
                          {keyword}
                        </span>
                      ))}
                    </div>
                    {user?.tier !== "pro" && result.ats_score.missing_keywords.length > 3 && (
                      <div className="mt-3 text-center">
                        <button
                          onClick={() => setShowUpgradeModal(true)}
                          className="text-sm text-amber-400 hover:text-amber-300 font-medium"
                        >
                          🔒 + {result.ats_score.missing_keywords.length - 3} more — Upgrade to see all
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Optimized Resume Tab */}
            {activeTab === "optimize" && (
              <div className="glass-card p-8 relative">
                {user?.tier !== "pro" && <PaywallOverlay onUpgradeClick={() => setShowUpgradeModal(true)} />}
                <div className="mb-6">
                  <h2 className="text-2xl font-bold text-white mb-2">Resume Optimization</h2>
                  <p className="text-sm text-slate-400">Compare your original resume with the AI-optimized version. Changes are highlighted for easy review.</p>
                </div>
                <ResumeComparison 
                  original={result?.original_resume || ""} 
                  optimized={result?.optimized_resume || ""} 
                  isFreePreview={user?.tier !== "pro"}
                />
                <div className="mt-6 flex gap-3">
                  <button
                    onClick={downloadDocx}
                    disabled={user?.tier !== "pro"}
                    className={`rounded-lg px-6 py-2.5 font-semibold transition-all flex items-center gap-2 ${
                      user?.tier === "pro"
                        ? "bg-gradient-to-r from-emerald-600 to-cyan-600 text-white hover:shadow-lg hover:shadow-emerald-500/20"
                        : "bg-slate-700/50 text-slate-400 cursor-not-allowed opacity-60"
                    }`}
                  >
                    📥 Download as DOCX
                    {user?.tier !== "pro" && <span>🔒</span>}
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const form = new FormData();
                        form.append("optimized_resume", result?.optimized_resume || "");
                        const res = await authenticatedFetch(`${API_BASE}/api/preview-docx`, {
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
            {activeTab === "skills" && result?.skill_gap && (
              <div className="space-y-6 relative">
                {user?.tier !== "pro" && <PaywallOverlay onUpgradeClick={() => setShowUpgradeModal(true)} />}
                <div className="grid gap-6 sm:grid-cols-2">
                  <div className="glass-card p-6">
                    <h3 className="mb-4 font-semibold text-emerald-400 flex items-center gap-2">✓ Matched Skills ({result?.skill_gap?.match_count || 0})</h3>
                    <div className="flex flex-wrap gap-2">
                      {result?.skill_gap?.matched_skills && result?.skill_gap?.matched_skills.length > 0 ? (
                        result?.skill_gap?.matched_skills?.slice(0, 20).map((skill) => (
                          <Tag key={skill} text={skill} variant="success" locked={user?.tier !== "pro"} />
                        ))
                      ) : (
                        <p className="text-sm text-slate-500">No matched skills</p>
                      )}
                    </div>
                  </div>
                  <div className="glass-card p-6">
                    <h3 className="mb-4 font-semibold text-red-400 flex items-center gap-2">✗ Missing Skills ({result?.skill_gap?.missing_skills?.length || 0})</h3>
                    <div className="flex flex-wrap gap-2">
                      {result?.skill_gap?.missing_skills && result?.skill_gap?.missing_skills.length > 0 ? (
                        result?.skill_gap?.missing_skills?.slice(0, 20).map((skill) => (
                          <a
                            key={skill}
                            href={`https://www.udemy.com/courses/search/?src=ukw&q=${encodeURIComponent(skill)}`}
                            target="_blank"
                            rel="sponsored noopener"
                            onClick={() => trackAffiliateClick(`SkillGap:${skill}`, result?.ats_score?.final_ats_score ?? 0)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30 hover:text-red-200 transition-colors"
                            title={`Learn ${skill} — close this gap`}
                          >
                            {skill}
                            <ExternalLink size={12} className="opacity-60" />
                          </a>
                        ))
                      ) : (
                        <p className="text-sm text-slate-500">Great! No missing critical skills</p>
                      )}
                    </div>
                  </div>
                </div>
                <div className={`glass-card p-6 ${getScoreBg(result?.skill_gap?.gap_score || 0)}`}>
                  <h3 className={`text-lg font-semibold mb-2 ${getScoreColor(result?.skill_gap?.gap_score || 0)}`}>Skill Gap Score: {(result?.skill_gap?.gap_score || 0).toFixed(1)}%</h3>
                  <p className="text-sm text-slate-300">
                    You have matched {result?.skill_gap?.match_count || 0} out of {result?.skill_gap?.total_required || 0} required skills.
                  </p>
                </div>
              </div>
            )}

            {/* Quality Tab */}
            {activeTab === "quality" && result?.resume_quality && (
              <div className="space-y-6 relative">
                {user?.tier !== "pro" && <PaywallOverlay onUpgradeClick={() => setShowUpgradeModal(true)} />}
                <div className="grid gap-6 sm:grid-cols-2">
                  <ScoreCard label="Overall Quality" score={result?.resume_quality?.overall_score || 0} icon="⭐" locked={user?.tier !== "pro"} />
                  <ScoreCard label="Readability" score={result?.resume_quality?.readability_score || 0} icon="📖" locked={user?.tier !== "pro"} />
                  <ScoreCard label="Formatting" score={result?.resume_quality?.formatting_score || 0} icon="🎨" locked={user?.tier !== "pro"} />
                  <ScoreCard label="Content" score={result?.resume_quality?.content_score || 0} icon="✏️" locked={user?.tier !== "pro"} />
                </div>
                <div className="glass-card p-6">
                  <h3 className="mb-4 font-semibold text-white">Feedback & Recommendations</h3>
                  <ul className="space-y-3">
                    {(result?.resume_quality?.feedback || []).map((item, i) => (
                      <li key={i} className="flex gap-3 text-sm text-slate-300">
                        <span className="text-emerald-400">•</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                {result?.writing_feedback?.suggestions && result.writing_feedback.suggestions.length > 0 && (
                  <div className="glass-card p-6">
                    <h3 className="mb-4 font-semibold text-white flex items-center gap-2">✍️ Writing Suggestions</h3>
                    <ul className="space-y-3">
                      {result.writing_feedback.suggestions.map((suggestion, i) => (
                        <li key={i} className="flex gap-3 text-sm text-slate-300">
                          <span className="text-blue-400 font-bold">{i + 1}.</span>
                          <span>{suggestion}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Keywords Tab */}
            {activeTab === "keywords" && (
              <div className="relative space-y-6">
                {user?.tier !== "pro" && <PaywallOverlay onUpgradeClick={() => setShowUpgradeModal(true)} />}
                <div className="glass-card p-6">
                  <h3 className="mb-4 font-semibold text-white">Extracted Keywords from Resume</h3>
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Keywords Found ({result?.keyword_heatmap?.keywords?.length || 0})</h4>
                      <div className="flex flex-wrap gap-2">
                        {(result?.keyword_heatmap?.keywords || []).slice(0, 30).map((k, idx) => (
                          <Tag key={idx} text={k} variant="success" locked={user?.tier !== "pro"} />
                        ))}
                      </div>
                      
                      {/* Ghost Keywords Teaser for Free Users */}
                      {user?.tier === "free" && result?.keyword_heatmap && result.keyword_heatmap.keywords.length > 3 && (
                        <div className="mt-4 p-4 bg-gradient-to-r from-amber-900/50 to-orange-900/50 border border-amber-600 rounded-lg text-center">
                          <div className="flex items-center justify-center gap-2 mb-2">
                            <span className="text-2xl">🔒</span>
                            <p className="text-amber-300 font-bold">
                              + {result.keyword_heatmap.keywords.length - 3} MORE KEYWORDS WAITING
                            </p>
                          </div>
                          <p className="text-xs text-amber-200 mb-3">
                            Pro users unlock all extracted keywords + see which ones ATS scanners prioritize
                          </p>
                          <button 
                            onClick={() => setShowUpgradeModal(true)}
                            className="w-full bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold py-2 px-4 rounded-lg transition-all transform hover:scale-105 shadow-lg"
                          >
                            🚀 Unlock All Keywords – Only $5/month
                          </button>
                        </div>
                      )}
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Recommended to Add</h4>
                      <div className="flex flex-wrap gap-2">
                        {(result?.ats_score?.recommended_keywords_to_add || []).slice(0, 20).map((k) => (
                          <Tag key={k} text={k} variant="success" locked={user?.tier !== "pro"} />
                        ))}
                      </div>
                    </div>
                    {/* Missing Keywords */}
                    {result?.ats_score?.missing_keywords && result.ats_score.missing_keywords.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium text-red-400 mb-3">Missing from Your Resume ({result.ats_score.missing_keywords.length})</h4>
                        <div className="flex flex-wrap gap-2">
                          {(user?.tier === "pro" ? result.ats_score.missing_keywords : result.ats_score.missing_keywords.slice(0, 3)).map((k) => (
                            <span
                              key={k}
                              title="Add this keyword to your resume to improve your ATS score"
                              className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30 transition-colors cursor-default"
                            >
                              {k}
                            </span>
                          ))}
                        </div>
                        {user?.tier !== "pro" && result.ats_score.missing_keywords.length > 3 && (
                          <button
                            onClick={() => setShowUpgradeModal(true)}
                            className="mt-2 text-sm text-amber-400 hover:text-amber-300 font-medium"
                          >
                            🔒 + {result.ats_score.missing_keywords.length - 3} more — Upgrade to see all
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
                <div className="glass-card p-6">
                  <h3 className="mb-4 font-semibold text-white">Top JD Keywords & Tools</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Required Skills</h4>
                      <div className="flex flex-wrap gap-2">
                        {(result?.jd_analysis?.required_skills || []).slice(0, 15).map((s) => (
                          <Tag key={s} text={s} variant="success" locked={user?.tier !== "pro"} />
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-3">Tools & Technologies</h4>
                      <div className="flex flex-wrap gap-2">
                        {(result?.jd_analysis?.tools || []).slice(0, 15).map((t) => (
                          <Tag key={t} text={t} locked={user?.tier !== "pro"} />
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

      {/* Auth Modal */}
      <AuthModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        onAuthSuccess={handleAuthSuccess}
      />

      {/* Upgrade Modal */}
      <UpgradeModal isOpen={showUpgradeModal} onClose={() => setShowUpgradeModal(false)} />

      {/* Tailor Rewrite Modal ($29 upsell) */}
      <TailorRewriteModal
        isOpen={showTailorModal}
        onClose={() => setShowTailorModal(false)}
        resumeText={result?.original_resume || ''}
        atsScore={result?.ats_score?.final_ats_score ?? 0}
        jobDescription={jdText}
        userEmail={user?.email || ''}
      />

      {/* Phase 3: Feedback Modal */}
      {sessionId && (
        <FeedbackModal
          isOpen={showFeedbackModal}
          sessionId={sessionId}
          onClose={() => setShowFeedbackModal(false)}
        />
      )}

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

import { useState } from "react";
import { getSupabaseClient } from "../lib/supabase";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAuthSuccess: (profile: any) => void;
}

type AuthTab = "login" | "signup";

interface FormState {
  email: string;
  password: string;
  confirmPassword: string;
}

export function AuthModal({ isOpen, onClose, onAuthSuccess }: AuthModalProps) {
  const [activeTab, setActiveTab] = useState<AuthTab>("login");
  const [form, setForm] = useState<FormState>({ email: "", password: "", confirmPassword: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const supabaseClient = getSupabaseClient();

  if (!isOpen) return null;

  // Check if Supabase is available
  if (!supabaseClient) {
    console.error("❌ AuthModal: supabaseClient is null - Supabase credentials not set!");
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-slate-950/90 border border-red-500/30 rounded-2xl shadow-2xl shadow-red-500/10 backdrop-blur-xl overflow-hidden">
          <div className="px-8 py-8">
            <div className="text-center mb-6">
              <div className="text-4xl mb-3">⚠️</div>
              <h2 className="text-2xl font-bold text-white mb-2">Configuration Error</h2>
            </div>
            <div className="space-y-4">
              <p className="text-slate-300 text-sm">
                Supabase credentials are not configured. To enable authentication:
              </p>
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm text-red-300 space-y-2">
                <p className="font-semibold">1. Create a Supabase project:</p>
                <p className="ml-2">Visit: https://supabase.com/dashboard</p>
                
                <p className="font-semibold mt-4">2. Get your credentials from Settings → API</p>
                
                <p className="font-semibold mt-4">3. Create <code className="bg-black/50 px-2 py-1 rounded">frontend/.env.local</code></p>
                <p className="ml-2 font-mono text-xs">VITE_SUPABASE_URL=https://...</p>
                <p className="ml-2 font-mono text-xs">VITE_SUPABASE_ANON_KEY=...</p>
                
                <p className="font-semibold mt-4">4. Restart dev server:</p>
                <p className="ml-2 font-mono text-xs">npm run dev</p>
              </div>
              <button
                onClick={onClose}
                className="w-full mt-6 px-4 py-2.5 rounded-lg bg-slate-700/50 text-slate-200 font-semibold hover:bg-slate-600/50 transition-all"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const handleInputChange = (field: keyof FormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setError(null);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.email || !form.password) {
      setError("Email and password are required");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      if (!supabaseClient.auth) {
        throw new Error("Supabase auth module not available");
      }

      const { data, error: authError } = await supabaseClient.auth.signInWithPassword({
        email: form.email,
        password: form.password,
      });

      if (authError) {
        throw new Error(authError.message);
      }

      if (data?.session) {
        // Cache token
        localStorage.setItem("auth_token", data.session.access_token);
        
        // Fetch user profile from backend
        const token = data.session.access_token;
        const apiBase = import.meta.env.VITE_API_BASE || "";
        const res = await fetch(`${apiBase}/api/me`, {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });

        if (res.ok) {
          const userProfile = await res.json();
          onAuthSuccess(userProfile);
          setForm({ email: "", password: "", confirmPassword: "" });
          onClose();
        } else if (res.status === 401) {
          throw new Error("Backend returned 401 - token may be invalid");
        } else {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed to load user profile");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.");
      console.error("Login error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.email || !form.password) {
      setError("Email and password are required");
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      if (!supabaseClient.auth) {
        throw new Error("Supabase auth module not available");
      }

      const { data, error: authError } = await supabaseClient.auth.signUp({
        email: form.email,
        password: form.password,
      });

      if (authError) {
        throw new Error(authError.message);
      }

      // Auto sign in after signup
      if (data?.user) {
        const { data: signInData, error: signInError } = await supabaseClient.auth.signInWithPassword({
          email: form.email,
          password: form.password,
        });

        if (signInError) {
          throw new Error("Account created but login failed. Please try logging in.");
        }

        if (signInData?.session) {
          localStorage.setItem("auth_token", signInData.session.access_token);

          // Fetch user profile
          const apiBase = import.meta.env.VITE_API_BASE || "";
          const res = await fetch(`${apiBase}/api/me`, {
            headers: {
              Authorization: `Bearer ${signInData.session.access_token}`,
              "Content-Type": "application/json",
            },
          });

          if (res.ok) {
            const userProfile = await res.json();
            onAuthSuccess(userProfile);
            setForm({ email: "", password: "", confirmPassword: "" });
            onClose();
          } else if (res.status === 401) {
            throw new Error("Backend returned 401 - ensure JWT_SECRET matches SUPABASE_JWT_SECRET");
          } else {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to load user profile");
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed. Please try again.");
      console.error("Sign up error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSocialAuth = (provider: "google" | "github") => {
    setError(`Social sign-in with ${provider} coming soon. Use email/password for now.`);
  };

  const handleDemoMode = () => {
    // Demo mode: Create mock user object
    const demoUser = {
      id: "demo-user-123",
      email: "demo@intelliresume.ai",
      full_name: "Demo User",
      tier: "free",
      scans_this_month: 1,
      scan_limit: 3,
      created_at: new Date().toISOString(),
    };
    // Demo mode removed — real auth required
    onAuthSuccess(demoUser);
    setForm({ email: "", password: "", confirmPassword: "" });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
      {/* Modal background with glassmorphism */}
      <div
        className="w-full max-w-md bg-slate-950/90 border border-emerald-500/30 rounded-2xl shadow-2xl shadow-emerald-500/10 backdrop-blur-xl overflow-hidden relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Glow effect */}
        <div className="absolute -inset-1 bg-gradient-to-r from-emerald-500/20 to-cyan-500/20 rounded-2xl blur opacity-0 group-hover:opacity-100 transition duration-1000 -z-10" />

        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-2 hover:bg-slate-800/50 rounded-lg transition-colors"
          aria-label="Close"
        >
          <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Header */}
        <div className="px-8 pt-8 pb-6 border-b border-emerald-500/20 bg-gradient-to-b from-slate-900/50 to-transparent">
          <h2 className="text-2xl font-bold text-white mb-1">Welcome to IntelliResume</h2>
          <p className="text-sm text-slate-400">Get AI-powered resume optimization in seconds</p>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-emerald-500/20 px-8 pt-6">
          <button
            onClick={() => setActiveTab("login")}
            className={`flex-1 pb-4 text-sm font-medium transition-all relative ${
              activeTab === "login" ? "text-emerald-400" : "text-slate-400 hover:text-slate-300"
            }`}
          >
            Sign In
            {activeTab === "login" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-500 to-cyan-500" />
            )}
          </button>
          <button
            onClick={() => setActiveTab("signup")}
            className={`flex-1 pb-4 text-sm font-medium transition-all relative ${
              activeTab === "signup" ? "text-emerald-400" : "text-slate-400 hover:text-slate-300"
            }`}
          >
            Create Account
            {activeTab === "signup" && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-500 to-cyan-500" />
            )}
          </button>
        </div>

        {/* Form Content */}
        <div className="px-8 py-8">
          {activeTab === "login" ? (
            <form onSubmit={handleLogin} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Email Address</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => handleInputChange("email", e.target.value)}
                  placeholder="you@example.com"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-white placeholder-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all outline-none hover:border-slate-600/75"
                  disabled={loading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Password</label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => handleInputChange("password", e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-white placeholder-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all outline-none hover:border-slate-600/75"
                  disabled={loading}
                />
              </div>
              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 rounded border-slate-600 accent-emerald-500" />
                  <span className="text-slate-400">Remember me</span>
                </label>
                <button type="button" className="text-emerald-400 hover:text-emerald-300 transition-colors">
                  Forgot password?
                </button>
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{error}</div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 text-white font-semibold hover:shadow-lg hover:shadow-emerald-500/30 transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />}
                {loading ? "Signing in..." : "Sign In"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleSignUp} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Email Address</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => handleInputChange("email", e.target.value)}
                  placeholder="you@example.com"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-white placeholder-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all outline-none hover:border-slate-600/75"
                  disabled={loading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Password</label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => handleInputChange("password", e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-white placeholder-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all outline-none hover:border-slate-600/75"
                  disabled={loading}
                />
                <p className="text-xs text-slate-500 mt-1">Minimum 8 characters</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Confirm Password</label>
                <input
                  type="password"
                  value={form.confirmPassword}
                  onChange={(e) => handleInputChange("confirmPassword", e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-white placeholder-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all outline-none hover:border-slate-600/75"
                  disabled={loading}
                />
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{error}</div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-emerald-600 to-cyan-600 text-white font-semibold hover:shadow-lg hover:shadow-emerald-500/30 transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />}
                {loading ? "Creating account..." : "Create Account"}
              </button>
            </form>
          )}

          {/* Demo Mode Button */}
          <button
            type="button"
            onClick={handleDemoMode}
            className="w-full mt-6 px-4 py-2.5 rounded-lg border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-all font-semibold text-sm"
          >
            📺 Try Demo Mode (skips email verification)
          </button>

          {/* Divider */}
          <div className="my-6 flex items-center gap-3">
            <div className="flex-1 h-px bg-slate-700/50" />
            <span className="text-xs text-slate-500 uppercase tracking-wider">Or continue with</span>
            <div className="flex-1 h-px bg-slate-700/50" />
          </div>

          {/* Social Auth Buttons */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => handleSocialAuth("google")}
              className="px-4 py-2.5 rounded-lg border border-slate-700/50 bg-slate-800/30 text-slate-300 hover:bg-slate-700/50 hover:border-slate-600 transition-all flex items-center justify-center gap-2 text-sm font-medium disabled:opacity-60"
              disabled={loading}
            >
              <svg
                className="w-4 h-4"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.85 4.05-1.26 1.24-3.23 2.62-6.74 2.62-5.386 0-9.74-4.3-9.74-9.64 0-5.34 4.354-9.64 9.74-9.64 2.93 0 5.26 1.26 6.92 2.9l2.46-2.48C18.023 2.495 15.17 0 12.48 0 5.802 0 .5 5.3.5 12s5.302 12 11.98 12c3.47 0 6.026-1.077 8.02-3.2 2.137-2.324 2.8-5.644 2.8-8.3 0-.76-.053-1.77-.175-2.48H12.48z" />
              </svg>
              Google
            </button>
            <button
              type="button"
              onClick={() => handleSocialAuth("github")}
              className="px-4 py-2.5 rounded-lg border border-slate-700/50 bg-slate-800/30 text-slate-300 hover:bg-slate-700/50 hover:border-slate-600 transition-all flex items-center justify-center gap-2 text-sm font-medium disabled:opacity-60"
              disabled={loading}
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.002 12.002 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              GitHub
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-emerald-500/20 bg-slate-900/30 text-center text-xs text-slate-500">
          By signing in, you agree to our{" "}
          <button className="text-emerald-400 hover:text-emerald-300 transition-colors">Terms of Service</button>
        </div>
      </div>
    </div>
  );
}

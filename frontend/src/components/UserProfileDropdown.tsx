import { useState } from "react";

interface UserProfileDropdownProps {
  user: {
    email: string;
    tier: "free" | "pro";
    scans_this_month: number;
    scan_limit: number;
  } | null;
  onLogout: () => void;
}

export function UserProfileDropdown({ user, onLogout }: UserProfileDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!user) return null;

  const tierConfig = {
    free: { label: "FREE", color: "bg-slate-600 text-slate-100" },
    pro: { label: "PRO", color: "bg-gradient-to-r from-emerald-600 to-cyan-600 text-white" },
  };

  const tier = tierConfig[user.tier];
  const scanPercentage = (user.scans_this_month / user.scan_limit) * 100;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-800/50 transition-colors border border-slate-700/50 hover:border-slate-600"
      >
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center">
          <span className="text-xs font-bold text-white">{user.email.charAt(0).toUpperCase()}</span>
        </div>
        <div className="hidden sm:flex flex-col items-start text-xs">
          <span className="text-slate-300 font-medium truncate max-w-[120px]">{user.email.split("@")[0]}</span>
          <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${tier.color}`}>{tier.label}</span>
        </div>
        <svg
          className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-slate-900 border border-slate-700/50 rounded-xl shadow-xl shadow-black/50 backdrop-blur-xl z-50 overflow-hidden">
          {/* Header */}
          <div className="p-4 border-b border-slate-700/50 bg-gradient-to-b from-slate-800/50 to-transparent">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center">
                <span className="text-sm font-bold text-white">{user.email.charAt(0).toUpperCase()}</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-white truncate">{user.email}</div>
                <div className={`text-xs font-bold px-2 py-0.5 rounded inline-block mt-1 ${tier.color}`}>
                  {tier.label}
                </div>
              </div>
            </div>
          </div>

          {/* Usage Stats */}
          <div className="px-4 py-4 border-b border-slate-700/50">
            <div className="text-xs text-slate-400 mb-2 font-medium">Monthly Scans</div>
            <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden border border-slate-600/50 mb-2">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-cyan-500 transition-all"
                style={{ width: `${Math.min(scanPercentage, 100)}%` }}
              />
            </div>
            <div className="text-xs text-slate-300">
              {user.scans_this_month} / {user.scan_limit} scans used
            </div>
            {user.tier === "free" && (
              <div className="mt-3 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300">
                💡 Upgrade to Pro for unlimited scans
              </div>
            )}
          </div>

          {/* Menu Items */}
          <div className="py-2">
            <button className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-slate-800/50 transition-colors flex items-center gap-3">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Settings
            </button>
            <button className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-slate-800/50 transition-colors flex items-center gap-3">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.172l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              Account
            </button>
            <button className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-slate-800/50 transition-colors flex items-center gap-3">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Help & Feedback
            </button>
          </div>

          {/* Logout */}
          <div className="border-t border-slate-700/50 p-2">
            <button
              onClick={() => {
                onLogout();
                setIsOpen(false);
              }}
              className="w-full px-4 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors flex items-center gap-3 rounded"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                />
              </svg>
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * src/lib/supabase.ts
 * 
 * Centralized Supabase client initialization as a singleton.
 * Handles:
 * - Supabase client creation with error handling
 * - Environment variable validation
 * - Export as singleton for app-wide use
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";

let supabaseClient: SupabaseClient | null = null;

/**
 * Initialize Supabase client (singleton pattern).
 * This should be called once at app startup.
 * 
 * @returns Supabase client instance or null if credentials missing
 */
export function initSupabaseClient(): SupabaseClient | null {
  // If already initialized, return cached instance
  if (supabaseClient) {
    return supabaseClient;
  }

  // Get credentials from import.meta.env (Vite) or window
  const SUPABASE_URL =
    import.meta.env.VITE_SUPABASE_URL ||
    (window as any).SUPABASE_URL ||
    process.env.REACT_APP_SUPABASE_URL;

  const SUPABASE_ANON_KEY =
    import.meta.env.VITE_SUPABASE_ANON_KEY ||
    (window as any).SUPABASE_ANON_KEY ||
    process.env.REACT_APP_SUPABASE_ANON_KEY;

  // Validate credentials
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    console.error(
      "❌ CRITICAL: Supabase credentials missing!",
      {
        hasUrl: !!SUPABASE_URL,
        hasKey: !!SUPABASE_ANON_KEY,
      },
      "Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in .env.local"
    );
    return null;
  }

  // Validate URL format
  if (!SUPABASE_URL.startsWith("https://")) {
    console.error(
      "❌ CRITICAL: SUPABASE_URL must start with https://",
      { SUPABASE_URL }
    );
    return null;
  }

  // Validate key length (should be ~40+ chars)
  if (SUPABASE_ANON_KEY.length < 20) {
    console.error(
      "❌ CRITICAL: SUPABASE_ANON_KEY seems invalid (too short)",
      { length: SUPABASE_ANON_KEY.length }
    );
    return null;
  }

  try {
    supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    console.log("✅ Supabase client initialized successfully");
    return supabaseClient;
  } catch (err) {
    console.error("❌ Failed to create Supabase client:", err);
    return null;
  }
}

/**
 * Get the Supabase client.
 * Call initSupabaseClient() first at app startup.
 * 
 * @returns Supabase client or null if not initialized
 */
export function getSupabaseClient(): SupabaseClient | null {
  return supabaseClient;
}

/**
 * Get the Supabase client or throw error if not available.
 * Use this when Supabase is required for operation.
 * 
 * @throws Error if client not initialized
 */
export function getSupabaseClientOrThrow(): SupabaseClient {
  if (!supabaseClient) {
    throw new Error(
      "Supabase client not initialized. Call initSupabaseClient() at app startup."
    );
  }
  return supabaseClient;
}

export default supabaseClient;

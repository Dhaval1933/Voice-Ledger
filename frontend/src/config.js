/**
 * API configuration for Kirana Khata frontend.
 * In development, defaults to '/api' which proxies to localhost:8000 via Vite.
 * In production (e.g. Vercel), can be overridden using VITE_API_BASE_URL in Vercel project settings.
 */
export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

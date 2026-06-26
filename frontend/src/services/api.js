/**
 * API fetch wrapper with token injection and 401 retry logic.
 *
 * Usage:
 *   1. Call `configureApi({ getAccessToken, refreshSession, logout })` once
 *      from the AuthProvider on mount.
 *   2. Use `apiFetch(path, options)` from anywhere in the app.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Module-level callbacks set by configureApi
let _getAccessToken = () => null;
let _refreshSession = () => Promise.reject(new Error('API not configured'));
let _logout = () => { };

/**
 * Configure the API module with auth callbacks.
 * Should be called once by AuthProvider on mount.
 *
 * @param {Object} config
 * @param {() => string|null} config.getAccessToken - Returns current access token
 * @param {() => Promise<any>} config.refreshSession - Attempts token refresh
 * @param {() => void} config.logout - Clears auth state and redirects to login
 */
export function configureApi({ getAccessToken, refreshSession, logout }) {
    _getAccessToken = getAccessToken;
    _refreshSession = refreshSession;
    _logout = logout;
}

/**
 * Fetch wrapper that injects the Authorization header and handles 401 retries.
 *
 * @param {string} path - API path (e.g. '/patterns/recent')
 * @param {RequestInit} [options={}] - Standard fetch options
 * @returns {Promise<Response>} - The fetch Response
 */
export async function apiFetch(path, options = {}) {
    const url = BASE_URL + path;

    // Build headers with token if available
    const headers = buildHeaders(options.headers);

    const response = await fetch(url, { ...options, headers });

    // If not a 401, return as-is
    if (response.status !== 401) {
        return response;
    }

    // 401 received — attempt one token refresh and retry
    try {
        await _refreshSession();
    } catch {
        // Refresh failed — redirect to login
        _logout();
        return response;
    }

    // Retry with the new token
    const retryHeaders = buildHeaders(options.headers);
    const retryResponse = await fetch(url, { ...options, headers: retryHeaders });

    if (retryResponse.status === 401) {
        // Still 401 after refresh — give up and redirect to login
        _logout();
        return retryResponse;
    }

    return retryResponse;
}

/**
 * Build a Headers object, merging the Authorization header when a token is available.
 *
 * @param {HeadersInit} [existing] - Existing headers from the caller
 * @returns {Headers}
 */
function buildHeaders(existing) {
    const headers = new Headers(existing);
    const token = _getAccessToken();
    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    return headers;
}

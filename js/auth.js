/**
 * Auth Module — Magic Link Email Authentication
 * 
 * Handles JWT token validation, session extension, and logout flows
 * Integrates with backend auth endpoints
 */

class AuthManager {
    constructor() {
        this.sessionKey = 'session_token';
        this.emailKey = 'user_email';
        this.expiryKey = 'session_expires';
        this.refreshInterval = 5 * 60 * 1000; // 5 minutes
    }

    /**
     * Request magic link via email
     */
    async requestMagicLink(email) {
        try {
            const response = await fetch('/app/mytheon-arena/auth/request', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Failed to request magic link');
            }

            return await response.json();

        } catch (error) {
            console.error('Magic link request failed:', error);
            throw error;
        }
    }

    /**
     * Verify JWT token from magic link
     */
    async verifyToken(token) {
        try {
            const response = await fetch('/app/mytheon-arena/auth/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Token validation failed');
            }

            const data = await response.json();
            this.setSession(data.sessionToken, data.email, data.expiresAt);
            
            return data;

        } catch (error) {
            console.error('Token verification failed:', error);
            throw error;
        }
    }

    /**
     * Store session in localStorage
     */
    setSession(token, email, expiresAt) {
        localStorage.setItem(this.sessionKey, token);
        localStorage.setItem(this.emailKey, email);
        localStorage.setItem(this.expiryKey, expiresAt);
    }

    /**
     * Get session token
     */
    getToken() {
        return localStorage.getItem(this.sessionKey);
    }

    /**
     * Get user email
     */
    getEmail() {
        return localStorage.getItem(this.emailKey);
    }

    /**
     * Check if session is valid
     */
    isValid() {
        const token = this.getToken();
        const expiresAt = localStorage.getItem(this.expiryKey);

        if (!token || !expiresAt) {
            return false;
        }

        // Check if expired
        return new Date(expiresAt) > new Date();
    }

    /**
     * Extend session duration
     */
    async extendSession() {
        const token = this.getToken();
        if (!token) return;

        try {
            const response = await fetch('/app/mytheon-arena/auth/extend', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem(this.expiryKey, data.expiresAt);
                return data;
            }

        } catch (error) {
            console.warn('Session extension failed:', error);
        }
    }

    /**
     * Clear session
     */
    logout() {
        localStorage.removeItem(this.sessionKey);
        localStorage.removeItem(this.emailKey);
        localStorage.removeItem(this.expiryKey);
    }

    /**
     * Start auto-refresh timer
     */
    startAutoRefresh() {
        setInterval(() => {
            if (this.isValid()) {
                this.extendSession();
            }
        }, this.refreshInterval);
    }

    /**
     * Get auth header for requests
     */
    getAuthHeader() {
        const token = this.getToken();
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    }
}

// Create global auth manager instance
window.authManager = new AuthManager();

// Auto-refresh sessions in the background
document.addEventListener('DOMContentLoaded', () => {
    window.authManager.startAutoRefresh();
});

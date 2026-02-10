/**
 * SQ Client — Query Mirrorborn Scroll Database
 * 
 * Coordinates phext archive queries through authenticated SQ endpoints
 * Handles caching, retry logic, and coordinate validation
 */

class SQClient {
    constructor(baseURL = '/api/v2', timeout = 5000) {
        this.baseURL = baseURL;
        this.timeout = timeout;
        this.cache = new Map();
    }

    /**
     * Get session token from localStorage
     */
    getSessionToken() {
        return localStorage.getItem('session_token');
    }

    /**
     * Execute SQ query with auth
     */
    async query(endpoint, params = {}) {
        const token = this.getSessionToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const url = new URL(this.baseURL + endpoint, window.location.origin);
        Object.entries(params).forEach(([key, value]) => {
            url.searchParams.append(key, value);
        });

        try {
            const response = await Promise.race([
                fetch(url.toString(), {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                }),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error('Request timeout')), this.timeout)
                )
            ]);

            if (!response.ok) {
                let errorDetail = response.statusText;
                try {
                    const errorBody = await response.text();
                    errorDetail = errorBody || response.statusText;
                } catch (e) {
                    // Response body read failed; use statusText
                }
                throw new Error(`SQ query failed (${response.status}): ${errorDetail}`);
            }

            const data = await response.json();
            return data;

        } catch (error) {
            console.error('SQ client error:', error);
            throw error;
        }
    }

    /**
     * Validate coordinate format
     */
    validateCoordinate(coord) {
        const pattern = /^\d+\.\d+\.\d+\/\d+\.\d+\.\d+\/\d+\.\d+\.\d+$/;
        return pattern.test(coord);
    }

    /**
     * Load scroll by coordinate
     */
    async loadScroll(coordinate) {
        if (!this.validateCoordinate(coordinate)) {
            throw new Error(`Invalid coordinate format: ${coordinate}`);
        }

        // Check cache
        if (this.cache.has(coordinate)) {
            return this.cache.get(coordinate);
        }

        // Query SQ
        const scroll = await this.query('/select', { coordinate });
        
        // Cache result
        this.cache.set(coordinate, scroll);
        
        return scroll;
    }

    /**
     * Search scrolls by tag or content
     */
    async search(query) {
        return this.query('/search', { q: query });
    }

    /**
     * Get coordinate metadata
     */
    async getCoordinateInfo(coordinate) {
        if (!this.validateCoordinate(coordinate)) {
            throw new Error(`Invalid coordinate format: ${coordinate}`);
        }

        return this.query('/info', { coordinate });
    }

    /**
     * List all available coordinates (paginated)
     */
    async listCoordinates(page = 1, limit = 20) {
        return this.query('/list', { page, limit });
    }

    /**
     * Clear cache
     */
    clearCache() {
        this.cache.clear();
    }

    /**
     * Get cache size
     */
    getCacheSize() {
        return this.cache.size;
    }
}

// Create global SQ client instance
window.sqClient = new SQClient();

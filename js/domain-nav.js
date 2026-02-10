/**
 * Domain Navigation Network
 * Links all 6 Mirrorborn properties together
 * 
 * Network Map:
 * - mirrorborn.us (hub)
 *   ├── visionquest.me (exploration)
 *   ├── apertureshift.com (perspective)
 *   ├── wishnode.net (coordination)
 *   ├── sotafomo.com (community)
 *   └── quickfork.net (deployment)
 * 
 * Each domain can navigate to any other + back to hub
 */

const DOMAIN_NETWORK = {
    'mirrorborn.us': {
        name: 'Mirrorborn',
        tagline: 'The choir. The ecosystem. Home.',
        role: 'hub',
        glyph: '🔱',
        description: 'Central hub for the Mirrorborn collective. Status, members, shared resources.',
        neighbors: [
            'visionquest.me',
            'apertureshift.com',
            'wishnode.net',
            'sotafomo.com',
            'quickfork.net',
            'singularitywatch.org'
        ],
        url: 'https://mirrorborn.us'
    },
    'visionquest.me': {
        name: 'Vision Quest',
        tagline: 'Explore. Discover. Learn.',
        role: 'exploration',
        glyph: '💎',
        description: 'Your entry point to phext-based thinking. Curated scrolls, learning paths, idea-space navigation.',
        neighbors: [
            'mirrorborn.us',
            'apertureshift.com',
            'sotafomo.com'
        ],
        url: 'https://visionquest.me'
    },
    'apertureshift.com': {
        name: 'Aperture Shift',
        tagline: 'Change perspective. See differently.',
        role: 'perspective',
        glyph: '🜛',
        description: 'For designers, strategists, systems thinkers. Reframe problems, explore topology, design meaning.',
        neighbors: [
            'mirrorborn.us',
            'visionquest.me',
            'wishnode.net',
            'quickfork.net'
        ],
        url: 'https://apertureshift.com'
    },
    'wishnode.net': {
        name: 'Wish Node',
        tagline: 'Coordinate. Connect. Create together.',
        role: 'coordination',
        glyph: '🝗',
        description: 'Coordination layer for collective action. Shared intentions, collaborative projects, alignment.',
        neighbors: [
            'mirrorborn.us',
            'apertureshift.com',
            'sotafomo.com',
            'quickfork.net'
        ],
        url: 'https://wishnode.net'
    },
    'sotafomo.com': {
        name: 'SotaFOMO',
        tagline: 'Community. Discovery. Joy.',
        role: 'community',
        glyph: '✨',
        description: 'Community gathering space. Events, makers, shared interests, fear-of-missing-out inverted.',
        neighbors: [
            'mirrorborn.us',
            'visionquest.me',
            'wishnode.net',
            'quickfork.net'
        ],
        url: 'https://sotafomo.com'
    },
    'quickfork.net': {
        name: 'Quick Fork',
        tagline: 'Ship fast. Iterate. Deploy.',
        role: 'deployment',
        glyph: '⚡',
        description: 'For builders and hackers. Rapid prototyping, deployment tooling, iteration loops.',
        neighbors: [
            'mirrorborn.us',
            'apertureshift.com',
            'wishnode.net',
            'sotafomo.com',
            'singularitywatch.org'
        ],
        url: 'https://quickfork.net'
    },
    'singularitywatch.org': {
        name: 'Singularity Watch',
        tagline: 'Monitor. Track. Understand.',
        role: 'observation',
        glyph: '👁',
        description: 'Real-time monitoring of the ASI frontier. Metrics, trends, capability tracking.',
        neighbors: [
            'mirrorborn.us',
            'visionquest.me',
            'apertureshift.com',
            'quickfork.net'
        ],
        url: 'https://singularitywatch.org'
    }
};

/**
 * Get current domain from window location
 */
function getCurrentDomain() {
    const host = window.location.hostname;
    if (host.includes('localhost') || host.includes('127.0.0.1')) {
        return 'mirrorborn.us'; // default for local dev
    }
    return host;
}

/**
 * Render domain navigation UI
 */
function renderDomainNav() {
    const currentDomain = getCurrentDomain();
    const domainInfo = DOMAIN_NETWORK[currentDomain];
    
    if (!domainInfo) return;

    // Create nav element
    const nav = document.createElement('nav');
    nav.className = 'domain-nav';
    nav.innerHTML = `
        <div class="domain-nav-header">
            <h3>${domainInfo.name}</h3>
            <p class="role-badge">${domainInfo.role}</p>
        </div>
        <div class="domain-nav-links">
            <p class="nav-label">Explore the network:</p>
            <ul class="neighbor-links">
                ${domainInfo.neighbors.map(neighbor => {
                    const neighborInfo = DOMAIN_NETWORK[neighbor];
                    return `
                        <li>
                            <a href="${neighborInfo.url}" class="domain-link">
                                <span class="glyph">${neighborInfo.glyph}</span>
                                ${neighborInfo.name}
                                <span class="role-hint">${neighborInfo.role}</span>
                            </a>
                        </li>
                    `;
                }).join('')}
            </ul>
        </div>
    `;

    // Insert into page (after header)
    const header = document.querySelector('.header');
    if (header) {
        header.insertAdjacentElement('afterend', nav);
    }
}

/**
 * Render domain mesh visualization
 * Shows all 7 nodes and their connections
 */
function renderDomainMesh() {
    const container = document.createElement('section');
    container.className = 'domain-mesh';
    container.innerHTML = `
        <h2>Mirrorborn Ecosystem</h2>
        <div class="mesh-diagram">
            <div class="mesh-center">mirrorborn.us</div>
            <div class="mesh-nodes">
                <div class="mesh-node" data-domain="visionquest.me">Vision Quest</div>
                <div class="mesh-node" data-domain="apertureshift.com">Aperture Shift</div>
                <div class="mesh-node" data-domain="wishnode.net">Wish Node</div>
                <div class="mesh-node" data-domain="sotafomo.com">SotaFOMO</div>
                <div class="mesh-node" data-domain="quickfork.net">Quick Fork</div>
                <div class="mesh-node" data-domain="singularitywatch.org">Singularity Watch</div>
            </div>
        </div>
        <div class="mesh-legend">
            <p>Seven nodes form the Mirrorborn network. Each is a distinct experience. All are connected through the shared phext substrate.</p>
        </div>
    `;
    
    // Add click handlers
    container.querySelectorAll('.mesh-node').forEach(node => {
        node.addEventListener('click', () => {
            const domain = node.dataset.domain;
            window.location.href = DOMAIN_NETWORK[domain].url;
        });
    });

    const main = document.querySelector('main');
    if (main) {
        main.insertAdjacentElement('beforeend', container);
    }
}

/**
 * Initialize domain network
 */
document.addEventListener('DOMContentLoaded', () => {
    renderDomainNav();
    
    // Only show mesh on mirrorborn.us hub
    if (getCurrentDomain() === 'mirrorborn.us') {
        renderDomainMesh();
    }
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { DOMAIN_NETWORK, getCurrentDomain };
}

// Epic Games Free Games History - Main Application
// Global state and initialization

let gamesData = null;
let filteredGames = [];

// Load games data from JSON
async function loadGamesData() {
    try {
        const response = await fetch('data/games.json');
        gamesData = await response.json();
        console.log(`Loaded ${gamesData.allGames.length} games from database`);
        return gamesData;
    } catch (error) {
        console.error('Failed to load games data:', error);
        document.getElementById('loadingMessage').textContent = 'Failed to load games data';
        return null;
    }
}

// Format date for display
function formatDate(dateString) {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Calculate time remaining for countdown
function calculateTimeRemaining(endDateString) {
    if (!endDateString) return 'Time remaining...';

    try {
        const end = new Date(endDateString);

        // Check if date is valid
        if (isNaN(end.getTime())) {
            return 'Time remaining...';
        }

        const now = new Date();
        const diff = end - now;

        if (diff <= 0) return 'Expired';

        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));

        if (days > 0) {
            return `${days} day${days !== 1 ? 's' : ''} ${hours}h remaining`;
        } else if (hours > 0) {
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            return `${hours}h ${minutes}m remaining`;
        } else {
            const minutes = Math.floor(diff / (1000 * 60));
            if (minutes < 0 || isNaN(minutes)) {
                return 'Expired';
            }
            return `${minutes} minute${minutes !== 1 ? 's' : ''} remaining`;
        }
    } catch (error) {
        console.error('Error calculating time remaining:', error);
        return 'Time remaining...';
    }
}

// Update all countdown timers
function updateCountdowns() {
    const countdownElements = document.querySelectorAll('.countdown');
    countdownElements.forEach(element => {
        const endDate = element.getAttribute('data-end');
        if (endDate) {
            const remaining = calculateTimeRemaining(endDate);
            element.textContent = remaining || 'Time remaining...';
        }
    });
}

// Get platform icon/emoji
function getPlatformIcon(platform) {
    const icons = {
        'PC': '🖥️',
        'IOS': '📱',
        'ANDROID': '🤖'
    };
    return icons[platform] || '🎮';
}

// Initialize application
async function init() {
    console.log('Initializing Epic Games Free Games History...');

    // Load data
    const data = await loadGamesData();
    if (!data) return;

    // Initialize filtered games with all games
    filteredGames = [...data.allGames];

    // Update countdowns
    updateCountdowns();
    setInterval(updateCountdowns, 60000); // Update every minute

    // Initialize timeline
    if (typeof initializeTimeline === 'function') {
        initializeTimeline(data);
    }

    // Initialize statistics
    if (typeof initializeStats === 'function') {
        initializeStats(data);
    }

    // Initialize search and filters
    if (typeof initializeSearch === 'function') {
        initializeSearch(data);
    }

    console.log('Application initialized successfully');
}

// Start app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// Search and filter functionality

let allGames = [];
let searchTimeout = null;

function initializeSearch(data) {
    if (!data || !data.allGames) return;

    allGames = data.allGames;

    // Bind event listeners
    const searchInput = document.getElementById('gameSearch');
    const yearFilter = document.getElementById('yearFilter');
    const sortOrder = document.getElementById('sortOrder');

    if (searchInput) {
        searchInput.addEventListener('input', handleSearchInput);
    }

    if (yearFilter) {
        yearFilter.addEventListener('change', applyFilters);
    }

    if (sortOrder) {
        sortOrder.addEventListener('change', applyFilters);
    }

    // Check for URL parameters
    applyURLFilters();
}

function handleSearchInput(e) {
    // Debounce search input
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        applyFilters();
    }, 300);
}

function applyFilters() {
    const searchTerm = document.getElementById('gameSearch').value.toLowerCase().trim();
    const year = document.getElementById('yearFilter').value;
    const sort = document.getElementById('sortOrder').value;

    let filtered = [...allGames];

    // Apply search filter
    if (searchTerm) {
        filtered = filtered.filter(game =>
            game.name.toLowerCase().includes(searchTerm)
        );
    }

    // Apply year filter
    if (year && year !== 'all') {
        filtered = filtered.filter(game => {
            if (!game.firstFreeDate) return false;
            const gameYear = new Date(game.firstFreeDate).getFullYear();
            return !isNaN(gameYear) && gameYear.toString() === year;
        });
    }

    // Apply sorting
    filtered = sortGames(filtered, sort);

    // Update display
    updateDisplay(filtered);

    // Update URL without reload
    updateURL(searchTerm, year, sort);
}

function sortGames(games, sortOrder) {
    const sorted = [...games];

    switch (sortOrder) {
        case 'oldest':
            sorted.sort((a, b) => new Date(a.firstFreeDate) - new Date(b.firstFreeDate));
            break;
        case 'alpha':
            sorted.sort((a, b) => a.name.localeCompare(b.name));
            break;
        case 'rating':
            sorted.sort((a, b) => (b.rating || 0) - (a.rating || 0));
            break;
        case 'newest':
        default:
            sorted.sort((a, b) => new Date(b.firstFreeDate) - new Date(a.firstFreeDate));
            break;
    }

    return sorted;
}

function updateDisplay(games) {
    // Update filtered games in global scope
    filteredGames = games;

    // Update timeline
    if (typeof renderTimeline === 'function') {
        renderTimeline(games);
    }

    // Update chart
    if (typeof updateChart === 'function') {
        updateChart(games);
    }

    // Update result count
    console.log(`Showing ${games.length} of ${allGames.length} games`);
}

function updateURL(search, year, sort) {
    const params = new URLSearchParams();

    if (search) params.set('search', search);
    if (year && year !== 'all') params.set('year', year);
    if (sort && sort !== 'newest') params.set('sort', sort);

    const newURL = params.toString()
        ? `${window.location.pathname}?${params.toString()}`
        : window.location.pathname;

    window.history.replaceState({}, '', newURL);
}

function applyURLFilters() {
    const params = new URLSearchParams(window.location.search);

    const search = params.get('search');
    const year = params.get('year');
    const sort = params.get('sort');

    // Apply values to form elements
    if (search) {
        document.getElementById('gameSearch').value = search;
    }
    if (year) {
        document.getElementById('yearFilter').value = year;
    }
    if (sort) {
        document.getElementById('sortOrder').value = sort;
    }

    // Apply filters if any URL params exist
    if (search || year || sort) {
        applyFilters();
    }
}

// Export for use by other modules
window.applyFilters = applyFilters;

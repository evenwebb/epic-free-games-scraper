// Timeline rendering and management

let currentGames = [];
let displayedGamesCount = 0;
const GAMES_PER_PAGE = 50;
let currentGameGroups = [];
let currentGroupIndex = 0;

function initializeTimeline(data) {
    currentGames = filteredGames;
    renderTimeline();
}

function renderTimeline(games = null) {
    if (games) {
        currentGames = games;
    }

    const timeline = document.getElementById('gameTimeline');
    const loadingMessage = document.getElementById('loadingMessage');
    const noResults = document.getElementById('noResults');

    // Hide loading
    loadingMessage.style.display = 'none';

    if (currentGames.length === 0) {
        timeline.innerHTML = '';
        noResults.style.display = 'block';
        removeLoadMoreButton();
        return;
    }

    noResults.style.display = 'none';

    // Group games by year and month
    const grouped = groupGamesByDate(currentGames);

    // Convert grouped structure to flat array for pagination
    currentGameGroups = [];
    Object.keys(grouped).sort((a, b) => b - a).forEach(year => {
        currentGameGroups.push({ type: 'year', year: year, months: grouped[year] });
    });

    // Clear timeline and reset
    timeline.innerHTML = '';
    displayedGamesCount = 0;
    currentGroupIndex = 0;

    // Load initial batch
    loadMoreGames();
}

function loadMoreGames() {
    const timeline = document.getElementById('gameTimeline');
    let gamesLoaded = 0;

    // Load games until we reach GAMES_PER_PAGE or run out
    while (currentGroupIndex < currentGameGroups.length && gamesLoaded < GAMES_PER_PAGE) {
        const group = currentGameGroups[currentGroupIndex];

        if (group.type === 'year') {
            const yearDiv = createYearSection(group.year, group.months);
            timeline.appendChild(yearDiv);

            // Count games in this year
            Object.values(group.months).forEach(monthGames => {
                gamesLoaded += monthGames.length;
            });
        }

        currentGroupIndex++;
    }

    displayedGamesCount += gamesLoaded;

    // Show/hide load more button
    if (currentGroupIndex >= currentGameGroups.length) {
        removeLoadMoreButton();
    } else {
        showLoadMoreButton();
    }
}

function showLoadMoreButton() {
    let loadMoreSection = document.getElementById('loadMoreSection');

    if (!loadMoreSection) {
        loadMoreSection = document.createElement('div');
        loadMoreSection.id = 'loadMoreSection';
        loadMoreSection.className = 'load-more';
        loadMoreSection.innerHTML = `
            <button id="loadMoreButton" class="load-more-button">
                Load More Games (${displayedGamesCount} of ${currentGames.length} shown)
            </button>
        `;

        const timeline = document.getElementById('gameTimeline');
        timeline.parentNode.appendChild(loadMoreSection);

        document.getElementById('loadMoreButton').addEventListener('click', loadMoreGames);
    } else {
        // Update button text
        const button = document.getElementById('loadMoreButton');
        if (button) {
            button.textContent = `Load More Games (${displayedGamesCount} of ${currentGames.length} shown)`;
        }
    }
}

function removeLoadMoreButton() {
    const loadMoreSection = document.getElementById('loadMoreSection');
    if (loadMoreSection) {
        loadMoreSection.remove();
    }
}

function groupGamesByDate(games) {
    const grouped = {};

    games.forEach(game => {
        const date = new Date(game.firstFreeDate);
        const year = date.getFullYear();
        const month = date.toLocaleDateString('en-US', { month: 'long' });

        if (!grouped[year]) {
            grouped[year] = {};
        }
        if (!grouped[year][month]) {
            grouped[year][month] = [];
        }
        grouped[year][month].push(game);
    });

    return grouped;
}

function createYearSection(year, months) {
    const yearDiv = document.createElement('div');
    yearDiv.className = 'timeline-year';

    const yearHeader = document.createElement('h3');
    yearHeader.className = 'timeline-year-header';
    yearHeader.textContent = year;
    yearDiv.appendChild(yearHeader);

    // Sort months chronologically
    const monthOrder = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December'];

    const sortedMonths = Object.keys(months).sort((a, b) => {
        return monthOrder.indexOf(b) - monthOrder.indexOf(a);
    });

    sortedMonths.forEach(month => {
        const monthDiv = createMonthSection(month, months[month]);
        yearDiv.appendChild(monthDiv);
    });

    return yearDiv;
}

function createMonthSection(month, games) {
    const monthDiv = document.createElement('div');
    monthDiv.className = 'timeline-month';

    const monthHeader = document.createElement('h4');
    monthHeader.className = 'timeline-month-header';
    monthHeader.textContent = `${month} (${games.length} games)`;
    monthDiv.appendChild(monthHeader);

    const gamesGrid = document.createElement('div');
    gamesGrid.className = 'timeline-games';

    games.forEach(game => {
        const gameCard = createGameCard(game);
        gamesGrid.appendChild(gameCard);
    });

    monthDiv.appendChild(gamesGrid);
    return monthDiv;
}

function createGameCard(game) {
    const card = document.createElement('div');
    card.className = 'game-card animate';
    card.setAttribute('data-game-id', game.id);
    card.setAttribute('data-platform', game.platform);

    // Image
    const imageDiv = document.createElement('div');
    imageDiv.className = 'game-card-image';

    if (game.image) {
        const img = document.createElement('img');
        img.src = game.image;
        img.alt = game.name;
        img.loading = 'lazy';
        imageDiv.appendChild(img);
    } else {
        const placeholder = document.createElement('div');
        placeholder.className = 'placeholder';
        placeholder.textContent = 'No Image Available';
        imageDiv.appendChild(placeholder);
    }

    // Body
    const body = document.createElement('div');
    body.className = 'game-card-body';

    const title = document.createElement('h3');
    title.className = 'game-card-title';
    const link = document.createElement('a');
    link.href = game.link;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = game.name;
    title.appendChild(link);

    const meta = document.createElement('div');
    meta.className = 'game-card-meta';

    const date = document.createElement('div');
    date.className = 'game-card-date';
    date.textContent = `Free: ${formatDate(game.firstFreeDate)}`;

    meta.appendChild(date);

    if (game.rating && game.rating > 0) {
        const rating = document.createElement('div');
        rating.className = 'game-card-rating';
        rating.textContent = `${game.rating.toFixed(2)}/5`;
        meta.appendChild(rating);
    }

    body.appendChild(title);
    body.appendChild(meta);

    card.appendChild(imageDiv);
    card.appendChild(body);

    return card;
}

// Export functions for use by search
window.renderTimeline = renderTimeline;
window.createGameCard = createGameCard;

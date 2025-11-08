// Upcoming Free Games - Display next free games section
// This module handles rendering the "Coming Soon" section

// Initialize upcoming games section
function initializeUpcoming(data) {
    if (!data || !data.upcomingGames) {
        console.log('No upcoming games data available');
        return;
    }

    renderUpcomingGames(data.upcomingGames);
}

// Render upcoming games grid
function renderUpcomingGames(upcomingGames) {
    const container = document.getElementById('upcomingGamesGrid');

    if (!container) {
        console.error('Upcoming games container not found');
        return;
    }

    // Clear existing content
    container.innerHTML = '';

    // Hide section if no upcoming games
    if (!upcomingGames || upcomingGames.length === 0) {
        const section = document.getElementById('upcoming-games');
        if (section) {
            section.style.display = 'none';
        }
        return;
    }

    // Show section and render each game
    const section = document.getElementById('upcoming-games');
    if (section) {
        section.style.display = 'block';
    }

    upcomingGames.forEach(game => {
        const card = createUpcomingGameCard(game);
        container.appendChild(card);
    });

    console.log(`Rendered ${upcomingGames.length} upcoming game(s)`);
}

// Create an upcoming game card
function createUpcomingGameCard(game) {
    const card = document.createElement('div');
    card.className = 'upcoming-card animate';

    // Image section
    const imageDiv = document.createElement('div');
    imageDiv.className = 'upcoming-card-image';

    if (game.image) {
        const img = document.createElement('img');
        img.src = game.image;
        img.alt = game.name;
        img.loading = 'lazy';
        imageDiv.appendChild(img);
    } else {
        const placeholder = document.createElement('div');
        placeholder.className = 'placeholder';
        placeholder.textContent = 'No Image';
        imageDiv.appendChild(placeholder);
    }

    // Badge for "UPCOMING"
    const badge = document.createElement('div');
    badge.className = 'upcoming-badge';
    badge.textContent = 'UPCOMING';
    imageDiv.appendChild(badge);

    // Content section
    const content = document.createElement('div');
    content.className = 'upcoming-card-content';

    // Game title
    const title = document.createElement('h3');
    title.className = 'upcoming-card-title';
    const titleLink = document.createElement('a');
    titleLink.href = game.link;
    titleLink.target = '_blank';
    titleLink.rel = 'noopener noreferrer';
    titleLink.textContent = game.name;
    title.appendChild(titleLink);
    content.appendChild(title);

    // Availability date
    const dateInfo = document.createElement('div');
    dateInfo.className = 'upcoming-card-date';

    if (game.startDate && game.endDate) {
        const startDate = formatDate(game.startDate);
        const endDate = formatDate(game.endDate);

        // Calculate when it starts
        const startDateObj = new Date(game.startDate);
        const now = new Date();
        const daysUntil = Math.ceil((startDateObj - now) / (1000 * 60 * 60 * 24));

        if (daysUntil > 0) {
            dateInfo.innerHTML = `
                <strong>Available in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}</strong><br>
                <span class="date-range">${startDate} - ${endDate}</span>
            `;
        } else if (daysUntil === 0) {
            dateInfo.innerHTML = `
                <strong>Available Today!</strong><br>
                <span class="date-range">${startDate} - ${endDate}</span>
            `;
        } else {
            dateInfo.innerHTML = `
                <strong>Available Now</strong><br>
                <span class="date-range">${startDate} - ${endDate}</span>
            `;
        }
    } else {
        dateInfo.innerHTML = '<span class="date-range">Date TBA</span>';
    }
    content.appendChild(dateInfo);

    // Rating (if available)
    if (game.rating && game.rating > 0) {
        const rating = document.createElement('div');
        rating.className = 'upcoming-card-rating';
        rating.textContent = `${game.rating.toFixed(2)} / 5.00`;
        content.appendChild(rating);
    }

    // CTA button
    const ctaButton = document.createElement('a');
    ctaButton.href = game.link;
    ctaButton.target = '_blank';
    ctaButton.rel = 'noopener noreferrer';
    ctaButton.className = 'upcoming-cta-button';
    ctaButton.textContent = 'View on Epic Store';
    content.appendChild(ctaButton);

    // Assemble card
    card.appendChild(imageDiv);
    card.appendChild(content);

    return card;
}

// Format date (same as app.js but local to module)
function formatDate(dateString) {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

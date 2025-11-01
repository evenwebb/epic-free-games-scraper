// Statistics and chart visualization

let gamesChart = null;

function initializeStats(data) {
    if (!data || !data.statistics) return;

    renderChart(data);
}

function renderChart(data) {
    const ctx = document.getElementById('gamesChart');
    if (!ctx) return;

    const gamesByYear = data.statistics.gamesByYear;
    const years = Object.keys(gamesByYear).sort();
    const counts = years.map(year => gamesByYear[year]);

    // Destroy existing chart if any
    if (gamesChart) {
        gamesChart.destroy();
    }

    // Create new chart
    gamesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: years,
            datasets: [{
                label: 'Free Games Per Year',
                data: counts,
                backgroundColor: 'rgba(0, 120, 242, 0.6)',
                borderColor: 'rgba(0, 120, 242, 1)',
                borderWidth: 2,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: 'Free Games by Year',
                    color: '#ffffff',
                    font: {
                        size: 18,
                        weight: 'bold'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(26, 26, 26, 0.9)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: '#0078f2',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y} games`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#a0a0a0',
                        stepSize: 20
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: '#a0a0a0'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// Update chart when filters change
function updateChart(filteredData) {
    if (!gamesChart || !filteredData) return;

    // Group filtered games by year
    const gamesByYear = {};
    filteredData.forEach(game => {
        const year = new Date(game.firstFreeDate).getFullYear();
        gamesByYear[year] = (gamesByYear[year] || 0) + 1;
    });

    const years = Object.keys(gamesByYear).sort();
    const counts = years.map(year => gamesByYear[year]);

    gamesChart.data.labels = years;
    gamesChart.data.datasets[0].data = counts;
    gamesChart.update();
}

// Export for use by search
window.updateChart = updateChart;

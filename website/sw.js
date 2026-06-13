const CACHE = 'epic-free-games-v1';
const URLS = ['/epic-free-games-scraper/', '/epic-free-games-scraper/css/styles.css',
    '/epic-free-games-scraper/css/timeline.css', '/epic-free-games-scraper/js/app.js',
    '/epic-free-games-scraper/js/search.js', '/epic-free-games-scraper/js/timeline.js',
    '/epic-free-games-scraper/data/games.json'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(URLS))));
self.addEventListener('fetch', e => e.respondWith(caches.match(e.request).then(r => r || fetch(e.request))));

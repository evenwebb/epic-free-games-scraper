import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
import os

class DatabaseManager:
    def __init__(self, db_path='output/epic_games.db'):
        self.db_path = db_path
        # Ensure output directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_database(self):
        """Create tables if they don't exist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Games table - stores unique games per platform
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    epic_id TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'PC',
                    name TEXT NOT NULL,
                    link TEXT NOT NULL,
                    epic_rating REAL,
                    image_filename TEXT,
                    sandbox_id TEXT,
                    mapping_slug TEXT,
                    product_slug TEXT,
                    url_slug TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(epic_id, platform)
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_games_name
                ON games(name)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_games_platform
                ON games(platform)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_games_created
                ON games(created_at DESC)
            """)

            # Promotions table - tracks each free game promotion period
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promotions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notified BOOLEAN DEFAULT 0,
                    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promotions_game_id
                ON promotions(game_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promotions_status
                ON promotions(status)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promotions_start_date
                ON promotions(start_date DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promotions_platform
                ON promotions(platform)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promotions_date_range
                ON promotions(start_date, end_date)
            """)

            # Performance: Composite index for common query pattern (status + platform)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_promotions_status_platform
                ON promotions(status, platform)
            """)

            # Scrape history table - audit trail of scraper runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scrape_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    games_found INTEGER,
                    new_games INTEGER,
                    current_promotions INTEGER,
                    upcoming_promotions INTEGER,
                    success BOOLEAN DEFAULT 1,
                    error_message TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_scrape_history_timestamp
                ON scrape_history(run_timestamp DESC)
            """)

            # Statistics cache table - pre-computed statistics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS statistics_cache (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_games INTEGER,
                    total_promotions INTEGER,
                    pc_games INTEGER,
                    ios_games INTEGER,
                    android_games INTEGER,
                    first_game_date TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    avg_games_per_week REAL,
                    most_common_month INTEGER
                )
            """)

            print(f"Database initialized at {self.db_path}")

    def batch_insert_or_update_games(self, games_data):
        """
        Batch insert or update multiple games.

        Args:
            games_data: List of dicts with keys: epic_id, name, link, platform, etc.

        Returns:
            Dict mapping (epic_id, platform) tuples to game_id
        """
        if not games_data:
            return {}

        game_id_map = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for game_data in games_data:
                epic_id = game_data['epic_id']
                platform = game_data.get('platform', 'PC')

                # Try to find existing game
                cursor.execute("""
                    SELECT id FROM games
                    WHERE epic_id = ? AND platform = ?
                """, (epic_id, platform))

                result = cursor.fetchone()

                if result:
                    # Update existing game
                    game_id = result['id']
                    cursor.execute("""
                        UPDATE games
                        SET name = ?,
                            link = ?,
                            epic_rating = COALESCE(?, epic_rating),
                            image_filename = COALESCE(?, image_filename),
                            sandbox_id = COALESCE(?, sandbox_id),
                            mapping_slug = COALESCE(?, mapping_slug),
                            product_slug = COALESCE(?, product_slug),
                            url_slug = COALESCE(?, url_slug),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (game_data['name'], game_data['link'],
                         game_data.get('epic_rating'), game_data.get('image_filename'),
                         game_data.get('sandbox_id'), game_data.get('mapping_slug'),
                         game_data.get('product_slug'), game_data.get('url_slug'),
                         game_id))
                else:
                    # Insert new game
                    cursor.execute("""
                        INSERT INTO games (epic_id, platform, name, link, epic_rating,
                                         image_filename, sandbox_id, mapping_slug,
                                         product_slug, url_slug)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (epic_id, platform, game_data['name'], game_data['link'],
                         game_data.get('epic_rating'), game_data.get('image_filename'),
                         game_data.get('sandbox_id'), game_data.get('mapping_slug'),
                         game_data.get('product_slug'), game_data.get('url_slug')))
                    game_id = cursor.lastrowid

                game_id_map[(epic_id, platform)] = game_id

        return game_id_map

    def insert_or_update_game(self, epic_id, name, link, platform='PC', epic_rating=None,
                             image_filename=None, sandbox_id=None, mapping_slug=None,
                             product_slug=None, url_slug=None):
        """Insert new game or update existing, returns game_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Try to find existing game
            cursor.execute("""
                SELECT id FROM games
                WHERE epic_id = ? AND platform = ?
            """, (epic_id, platform))

            result = cursor.fetchone()

            if result:
                # Update existing game
                game_id = result['id']
                cursor.execute("""
                    UPDATE games
                    SET name = ?,
                        link = ?,
                        epic_rating = COALESCE(?, epic_rating),
                        image_filename = COALESCE(?, image_filename),
                        sandbox_id = COALESCE(?, sandbox_id),
                        mapping_slug = COALESCE(?, mapping_slug),
                        product_slug = COALESCE(?, product_slug),
                        url_slug = COALESCE(?, url_slug),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (name, link, epic_rating, image_filename, sandbox_id,
                     mapping_slug, product_slug, url_slug, game_id))
            else:
                # Insert new game
                cursor.execute("""
                    INSERT INTO games (epic_id, platform, name, link, epic_rating,
                                     image_filename, sandbox_id, mapping_slug,
                                     product_slug, url_slug)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (epic_id, platform, name, link, epic_rating, image_filename,
                     sandbox_id, mapping_slug, product_slug, url_slug))
                game_id = cursor.lastrowid

            return game_id

    def batch_insert_promotions(self, promotions_data):
        """
        Batch insert multiple promotions, avoids duplicates.

        Args:
            promotions_data: List of dicts with keys: game_id, start_date, end_date, status, platform
        """
        if not promotions_data:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for promo_data in promotions_data:
                # Check if this exact promotion already exists
                cursor.execute("""
                    SELECT id FROM promotions
                    WHERE game_id = ? AND start_date = ? AND end_date = ?
                """, (promo_data['game_id'], promo_data['start_date'], promo_data['end_date']))

                if cursor.fetchone():
                    # Promotion already exists, skip
                    continue

                cursor.execute("""
                    INSERT INTO promotions (game_id, start_date, end_date, status, platform, notified)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (promo_data['game_id'], promo_data['start_date'], promo_data['end_date'],
                     promo_data['status'], promo_data.get('platform', 'PC'),
                     int(promo_data.get('notified', False))))

    def insert_promotion(self, game_id, start_date, end_date, status, platform='PC', notified=False):
        """Insert new promotion record, avoids duplicates"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if this exact promotion already exists
            cursor.execute("""
                SELECT id FROM promotions
                WHERE game_id = ? AND start_date = ? AND end_date = ?
            """, (game_id, start_date, end_date))

            if cursor.fetchone():
                # Promotion already exists, skip
                return

            cursor.execute("""
                INSERT INTO promotions (game_id, start_date, end_date, status, platform, notified)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (game_id, start_date, end_date, status, platform, int(notified)))

    def update_promotion_status(self):
        """Update status of all promotions based on current time"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            # Update to 'expired' if end_date has passed
            cursor.execute("""
                UPDATE promotions
                SET status = 'expired', last_checked = CURRENT_TIMESTAMP
                WHERE status != 'expired' AND end_date < ?
            """, (now,))

            # Update to 'current' if start_date has passed and end_date hasn't
            cursor.execute("""
                UPDATE promotions
                SET status = 'current', last_checked = CURRENT_TIMESTAMP
                WHERE status = 'upcoming' AND start_date <= ? AND end_date >= ?
            """, (now, now))

            print(f"Updated promotion statuses at {now}")

    def get_current_games(self, platform=None):
        """Get all currently free games, optionally filtered by platform"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if platform:
                cursor.execute("""
                    SELECT g.*, p.start_date, p.end_date, p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'current' AND g.platform = ?
                    GROUP BY g.id
                    ORDER BY p.start_date DESC
                """, (platform,))
            else:
                cursor.execute("""
                    SELECT g.*, p.start_date, p.end_date, p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'current'
                    GROUP BY g.id
                    ORDER BY g.platform, p.start_date DESC
                """)

            return [dict(row) for row in cursor.fetchall()]

    def get_upcoming_games(self, platform=None):
        """Get all upcoming free games, optionally filtered by platform"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if platform:
                cursor.execute("""
                    SELECT g.*, p.start_date, p.end_date, p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'upcoming' AND g.platform = ?
                    GROUP BY g.id
                    ORDER BY p.start_date ASC
                """, (platform,))
            else:
                cursor.execute("""
                    SELECT g.*, p.start_date, p.end_date, p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'upcoming'
                    GROUP BY g.id
                    ORDER BY p.start_date ASC
                """)

            return [dict(row) for row in cursor.fetchall()]

    def get_all_games_chronological(self, platform=None, limit=None):
        """Get all games sorted by first promotion date, optionally filtered by platform"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if platform:
                query = """
                    SELECT g.*,
                           MIN(p.start_date) as first_free_date,
                           MAX(p.end_date) as last_free_date,
                           GROUP_CONCAT(DISTINCT p.status) as all_statuses
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE g.platform = ?
                    GROUP BY g.id
                    ORDER BY first_free_date DESC
                """
                params = (platform,)
            else:
                query = """
                    SELECT g.*,
                           MIN(p.start_date) as first_free_date,
                           MAX(p.end_date) as last_free_date,
                           GROUP_CONCAT(DISTINCT p.status) as all_statuses
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    GROUP BY g.id
                    ORDER BY first_free_date DESC
                """
                params = ()

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def record_scrape_run(self, games_found, new_games, current, upcoming, success=True, error=None):
        """Log scraper execution"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scrape_history
                (games_found, new_games, current_promotions, upcoming_promotions, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (games_found, new_games, current, upcoming, int(success), error))
            print(f"Recorded scrape run: {games_found} games found, {new_games} new")

    def update_statistics_cache(self):
        """Recalculate and cache statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Calculate statistics
            cursor.execute("SELECT COUNT(*) as total FROM games")
            total_games = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as total FROM promotions")
            total_promotions = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as total FROM games WHERE platform = 'PC'")
            pc_games = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as total FROM games WHERE platform = 'iOS'")
            ios_games = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as total FROM games WHERE platform = 'Android'")
            android_games = cursor.fetchone()['total']

            cursor.execute("SELECT MIN(start_date) as first_date FROM promotions")
            first_game_date = cursor.fetchone()['first_date']

            # Calculate average games per week
            if first_game_date:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_promos,
                        JULIANDAY('now') - JULIANDAY(?) as days_elapsed
                    FROM promotions
                """, (first_game_date,))
                result = cursor.fetchone()
                if result['days_elapsed'] > 0:
                    avg_per_week = (result['total_promos'] / result['days_elapsed']) * 7
                else:
                    avg_per_week = 0
            else:
                avg_per_week = 0

            # Find most common month
            cursor.execute("""
                SELECT CAST(strftime('%m', start_date) AS INTEGER) as month, COUNT(*) as count
                FROM promotions
                GROUP BY month
                ORDER BY count DESC
                LIMIT 1
            """)
            most_common_result = cursor.fetchone()
            most_common_month = most_common_result['month'] if most_common_result else None

            # Insert or update statistics
            cursor.execute("""
                INSERT OR REPLACE INTO statistics_cache
                (id, total_games, total_promotions, pc_games, ios_games, android_games,
                 first_game_date, avg_games_per_week, most_common_month, last_updated)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (total_games, total_promotions, pc_games, ios_games, android_games,
                 first_game_date, avg_per_week, most_common_month))

            print(f"Statistics updated: {total_games} total games ({pc_games} PC, {ios_games} iOS, {android_games} Android)")

    def get_statistics(self):
        """Retrieve cached statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM statistics_cache WHERE id = 1")
            result = cursor.fetchone()
            return dict(result) if result else {}

    def get_platform_counts(self):
        """Get game counts by platform"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT platform, COUNT(*) as count
                FROM games
                GROUP BY platform
                ORDER BY count DESC
            """)
            return {row['platform']: row['count'] for row in cursor.fetchall()}

    def get_games_by_year(self, platform=None):
        """Get game counts grouped by year"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if platform:
                cursor.execute("""
                    SELECT strftime('%Y', p.start_date) as year, COUNT(DISTINCT g.id) as count
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE g.platform = ?
                    GROUP BY year
                    ORDER BY year
                """, (platform,))
            else:
                cursor.execute("""
                    SELECT strftime('%Y', start_date) as year, COUNT(*) as count
                    FROM promotions
                    GROUP BY year
                    ORDER BY year
                """)

            return {row['year']: row['count'] for row in cursor.fetchall()}

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
        conn.execute("PRAGMA journal_mode=WAL")
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
                    original_price_cents INTEGER,
                    currency_code TEXT,
                    sandbox_id TEXT,
                    mapping_slug TEXT,
                    product_slug TEXT,
                    url_slug TEXT,
                    description TEXT,
                    seller_name TEXT,
                    offer_type TEXT,
                    effective_date TIMESTAMP,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(epic_id, platform)
                )
            """)
            
            # Add price columns if they don't exist (migration for existing databases)
            cursor.execute("PRAGMA table_info(games)")
            cols = {row[1] for row in cursor.fetchall()}
            if 'original_price_cents' not in cols:
                cursor.execute("ALTER TABLE games ADD COLUMN original_price_cents INTEGER")
            if 'currency_code' not in cols:
                cursor.execute("ALTER TABLE games ADD COLUMN currency_code TEXT")
            if 'last_checked' not in cols:
                cursor.execute("ALTER TABLE games ADD COLUMN last_checked TIMESTAMP")
            for col, col_type in [
                ('description', 'TEXT'),
                ('seller_name', 'TEXT'),
                ('offer_type', 'TEXT'),
                ('effective_date', 'TIMESTAMP'),
            ]:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE games ADD COLUMN {col} {col_type}")

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
                ON games(created_at)
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
                ON promotions(start_date)
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
                    most_common_month INTEGER,
                    total_value_cents INTEGER,
                    avg_price_cents REAL,
                    current_year_value_cents INTEGER
                )
            """)
            
            # Add price statistics columns if they don't exist (migration)
            cursor.execute("PRAGMA table_info(statistics_cache)")
            sc_cols = {row[1] for row in cursor.fetchall()}
            if 'total_value_cents' not in sc_cols:
                cursor.execute("ALTER TABLE statistics_cache ADD COLUMN total_value_cents INTEGER")
            if 'avg_price_cents' not in sc_cols:
                cursor.execute("ALTER TABLE statistics_cache ADD COLUMN avg_price_cents REAL")
            if 'current_year_value_cents' not in sc_cols:
                cursor.execute("ALTER TABLE statistics_cache ADD COLUMN current_year_value_cents INTEGER")

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

            # Single query: fetch all existing games with their current prices
            cursor.execute(
                "SELECT id, epic_id, platform, original_price_cents FROM games"
            )
            existing = {(row['epic_id'], row['platform']): (row['id'], row['original_price_cents'])
                        for row in cursor.fetchall()}

            inserts = []
            for game_data in games_data:
                epic_id = game_data['epic_id']
                platform = game_data.get('platform', 'PC')
                key = (epic_id, platform)
                existing_info = existing.get(key)

                if existing_info is not None:
                    game_id, existing_price = existing_info
                    game_id_map[key] = game_id

                    # Preserve first captured price
                    price = game_data.get('original_price_cents')
                    set_price = (
                        price is not None and price > 0 and existing_price is None
                    )
                    if set_price:
                        cursor.execute("""
                            UPDATE games
                            SET name = ?, link = ?,
                                epic_rating = COALESCE(?, epic_rating),
                                image_filename = COALESCE(?, image_filename),
                                original_price_cents = ?, currency_code = ?,
                                sandbox_id = COALESCE(?, sandbox_id),
                                mapping_slug = COALESCE(?, mapping_slug),
                                product_slug = COALESCE(?, product_slug),
                                url_slug = COALESCE(?, url_slug),
                                description = COALESCE(?, description),
                                seller_name = COALESCE(?, seller_name),
                                offer_type = COALESCE(?, offer_type),
                                effective_date = COALESCE(?, effective_date),
                                last_checked = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (game_data['name'], game_data['link'],
                              game_data.get('epic_rating'), game_data.get('image_filename'),
                              price, game_data.get('currency_code'),
                              game_data.get('sandbox_id'), game_data.get('mapping_slug'),
                              game_data.get('product_slug'), game_data.get('url_slug'),
                              game_data.get('description'), game_data.get('seller_name'),
                              game_data.get('offer_type'), game_data.get('effective_date'),
                              game_id))
                    else:
                        cursor.execute("""
                            UPDATE games
                            SET name = ?, link = ?,
                                epic_rating = COALESCE(?, epic_rating),
                                image_filename = COALESCE(?, image_filename),
                                sandbox_id = COALESCE(?, sandbox_id),
                                mapping_slug = COALESCE(?, mapping_slug),
                                product_slug = COALESCE(?, product_slug),
                                url_slug = COALESCE(?, url_slug),
                                description = COALESCE(?, description),
                                seller_name = COALESCE(?, seller_name),
                                offer_type = COALESCE(?, offer_type),
                                effective_date = COALESCE(?, effective_date),
                                last_checked = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (game_data['name'], game_data['link'],
                              game_data.get('epic_rating'), game_data.get('image_filename'),
                              game_data.get('sandbox_id'), game_data.get('mapping_slug'),
                              game_data.get('product_slug'), game_data.get('url_slug'),
                              game_data.get('description'), game_data.get('seller_name'),
                              game_data.get('offer_type'), game_data.get('effective_date'),
                              game_id))
                else:
                    inserts.append((
                        epic_id, platform, game_data['name'], game_data['link'],
                        game_data.get('epic_rating'), game_data.get('image_filename'),
                        game_data.get('original_price_cents'), game_data.get('currency_code'),
                        game_data.get('sandbox_id'), game_data.get('mapping_slug'),
                        game_data.get('product_slug'), game_data.get('url_slug'),
                        game_data.get('description'), game_data.get('seller_name'),
                        game_data.get('offer_type'), game_data.get('effective_date'),
                    ))

            if inserts:
                cursor.executemany("""
                    INSERT INTO games (epic_id, platform, name, link, epic_rating,
                                     image_filename, original_price_cents, currency_code,
                                     sandbox_id, mapping_slug, product_slug, url_slug,
                                     description, seller_name, offer_type, effective_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, inserts)
                # Map IDs for newly inserted rows
                cursor.execute(
                    "SELECT id, epic_id, platform FROM games"
                )
                for row in cursor.fetchall():
                    key = (row['epic_id'], row['platform'])
                    if key not in game_id_map:
                        game_id_map[key] = row['id']

        return game_id_map

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
                    SELECT g.*, MAX(p.start_date) as start_date, MAX(p.end_date) as end_date,
                           p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'current' AND g.platform = ?
                    GROUP BY g.id
                    ORDER BY MAX(p.start_date) DESC
                """, (platform,))
            else:
                cursor.execute("""
                    SELECT g.*, MAX(p.start_date) as start_date, MAX(p.end_date) as end_date,
                           p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'current'
                    GROUP BY g.id
                    ORDER BY g.platform, MAX(p.start_date) DESC
                """)

            return [dict(row) for row in cursor.fetchall()]

    def get_upcoming_games(self, platform=None):
        """Get all upcoming free games, optionally filtered by platform"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if platform:
                cursor.execute("""
                    SELECT g.*, MIN(p.start_date) as start_date, MIN(p.end_date) as end_date,
                           p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'upcoming' AND g.platform = ?
                    GROUP BY g.id
                    ORDER BY MIN(p.start_date) ASC
                """, (platform,))
            else:
                cursor.execute("""
                    SELECT g.*, MIN(p.start_date) as start_date, MIN(p.end_date) as end_date,
                           p.status
                    FROM games g
                    JOIN promotions p ON g.id = p.game_id
                    WHERE p.status = 'upcoming'
                    GROUP BY g.id
                    ORDER BY MIN(p.start_date) ASC
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
                now_utc = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_promos,
                        JULIANDAY(?) - JULIANDAY(?) as days_elapsed
                    FROM promotions
                """, (now_utc, first_game_date))
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

            # Calculate price statistics
            cursor.execute("""
                SELECT 
                    SUM(original_price_cents) as total_value,
                    AVG(original_price_cents) as avg_price
                FROM games 
                WHERE platform = 'PC' AND original_price_cents IS NOT NULL
            """)
            price_result = cursor.fetchone()
            total_value_cents = int(price_result['total_value']) if price_result and price_result['total_value'] is not None else None
            avg_price_cents = float(price_result['avg_price']) if price_result and price_result['avg_price'] is not None else None
            
            # Calculate current year value
            current_year = datetime.now().strftime('%Y')
            cursor.execute("""
                SELECT SUM(g.original_price_cents) as year_value
                FROM games g
                JOIN promotions p ON g.id = p.game_id
                WHERE g.platform = 'PC' 
                AND g.original_price_cents IS NOT NULL
                AND strftime('%Y', p.start_date) = ?
            """, (current_year,))
            year_result = cursor.fetchone()
            current_year_value_cents = int(year_result['year_value']) if year_result and year_result['year_value'] else None

            # Insert or update statistics
            cursor.execute("""
                INSERT OR REPLACE INTO statistics_cache
                (id, total_games, total_promotions, pc_games, ios_games, android_games,
                 first_game_date, avg_games_per_week, most_common_month,
                 total_value_cents, avg_price_cents, current_year_value_cents, last_updated)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (total_games, total_promotions, pc_games, ios_games, android_games,
                 first_game_date, avg_per_week, most_common_month,
                 total_value_cents, avg_price_cents, current_year_value_cents))

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

    def get_stale_games(self, days: int = 30) -> list[dict]:
        """Find games not seen by the scraper in the given number of days (possibly delisted)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM games
                WHERE datetime(last_checked) < datetime('now', ?)
                ORDER BY last_checked ASC
            """, (f'-{int(days)} days',))
            return [dict(row) for row in cursor.fetchall()]

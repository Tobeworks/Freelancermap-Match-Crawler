import sqlite3
from datetime import datetime
import pandas as pd
import time
import random
import math
import json
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

load_dotenv()


FREELANCERMAP_USERNAME = os.getenv('FREELANCERMAP_USERNAME')
FREELANCERMAP_PASSWORD = os.getenv('FREELANCERMAP_PASSWORD')

MAX_PAGES = 100
MIN_SCORE = 35

PROFILE = {
    'skills': [
        'Python', 'JavaScript', 'React', 'Vue', 'MySQL',
        'HTML', 'CSS', 'PHP', 'GCP', 'AWS', 'Cloud',
        'AI', 'Frontend', 'Vue.js', 'JS'
    ],
    'preferred_keywords': [
        'Webentwicklung', 'Backend', 'Frontend', 'Fullstack',
        'API', 'Wordpress', 'GCP', 'AWS', 'Cloud', 'AI', 'OpenAI'
    ],
    'excluded_keywords': ['SAP', 'Drupal']
}


class FreelancermapDatabase:
    def __init__(self, db_path="freelancermap.db"):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                link TEXT UNIQUE,
                company TEXT,
                description TEXT,
                keywords TEXT,
                created_date DATETIME,
                is_top_project BOOLEAN,
                is_endcustomer BOOLEAN,
                scrape_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT,
                link TEXT,
                company TEXT,
                description TEXT,
                keywords TEXT,
                created_date DATETIME,
                is_top_project BOOLEAN,
                is_endcustomer BOOLEAN,
                match_score FLOAT,
                match_debug TEXT,
                match_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        """)
        self.conn.commit()


class FreelancermapScraper:
    def __init__(self, db, username, password, max_pages=2):
        self.db = db
        self.base_url = "https://www.freelancermap.de"
        self.username = username
        self.password = password
        self.max_pages = max_pages
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    def _ensure_browser(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._ctx = self._browser.new_context(
                locale='de-DE',
                user_agent=(
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Safari/537.36'
                ),
            )
            self._page = self._ctx.new_page()

    def close(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None
        self._ctx = None
        self._page = None

    def __del__(self):
        self.close()

    def login(self):
        try:
            print("Starte Login-Prozess...")
            self._ensure_browser()

            print("Lade Login-Seite...")
            self._page.goto(f"{self.base_url}/login", wait_until='domcontentloaded', timeout=20000)

            print("Führe Login durch...")
            self._page.fill('input[name="login"]', self.username)
            self._page.fill('input[name="password"]', self.password)

            with self._page.expect_navigation(wait_until='domcontentloaded', timeout=15000):
                self._page.click('button[type="submit"], input[type="submit"]')

            print(f"Response URL: {self._page.url}")

            time.sleep(1)
            self._page.goto(f"{self.base_url}/mein_account.html", wait_until='domcontentloaded', timeout=15000)

            content = self._page.content()
            if any(x in content for x in ['Mein Konto', 'Profil', 'Logout', 'Abmelden']):
                print("Login erfolgreich!")
                return True

            print("Login fehlgeschlagen: Keine Login-Indikatoren gefunden")
            return False

        except Exception as e:
            print(f"Fehler beim Login: {str(e)}")
            return False

    def get_page_url(self, page_number):
        params = [
            "contractTypes[]=contracting",
            "remoteInPercent[]=100",
            "countries[]=1",
            "countries[]=2",
            "countries[]=3",
            "sort=1",
            f"pagenr={page_number}",
        ]
        return f"{self.base_url}/projekte?{'&'.join(params)}"

    def get_page(self, page_number):
        url = self.get_page_url(page_number)
        print(f"\nAbrufen von Seite {page_number}")
        print(f"URL: {url}")

        captured_json = []

        def _on_response(response):
            # Intercept JSON responses that might contain project data
            if response.status != 200:
                return
            ct = response.headers.get('content-type', '')
            if 'json' not in ct:
                return
            try:
                data = response.json()
                if isinstance(data, list) and data and isinstance(data[0], dict) and 'title' in data[0]:
                    captured_json.extend(data)
                elif isinstance(data, dict):
                    for key in ('projects', 'hits', 'items', 'results', 'data'):
                        if key in data and isinstance(data[key], list):
                            captured_json.extend(data[key])
                            break
            except Exception:
                pass

        try:
            self._page.on('response', _on_response)
            self._page.goto(url, wait_until='networkidle', timeout=30000)
            self._page.remove_listener('response', _on_response)

            print(f"Status Code: 200 (Playwright)")

            content = self._page.content()

            if "Bitte melden Sie sich an" in content:
                print("Login-Session abgelaufen, versuche erneuten Login...")
                if self.login():
                    return self.get_page(page_number)
                return []

            # Primary: JSON captured from network responses (React API calls)
            if captured_json:
                print(f"Projekte via API-Antwort: {len(captured_json)}")
                projects = [self._parse_json_project(p, is_top=False) for p in captured_json]
                return [p for p in projects if p]

            soup = BeautifulSoup(content, 'html.parser')

            # Secondary: JSON embedded in script tag (top_projects etc.)
            projects = self._extract_from_script_json(soup)
            if projects:
                print(f"Projekte via eingebettetem JSON: {len(projects)}")
                return projects

            # Tertiary: rendered HTML elements
            projects = self._extract_from_html(soup)
            if projects:
                print(f"Projekte via HTML: {len(projects)}")
                return projects

            print("Keine Projekte auf dieser Seite gefunden!")
            return []

        except Exception as e:
            print(f"Fehler beim Laden der Seite {page_number}: {str(e)}")
            self._page.remove_listener('response', _on_response)
            return []

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_from_script_json(self, soup):
        """Parse projects embedded in the React-on-Rails JSON script tag."""
        script = soup.find(
            'script',
            class_='js-react-on-rails-component',
            attrs={'data-component-name': 'ProjectSearch'},
        )
        if not script or not script.string:
            return []
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return []

        projects = []
        for key in ('projects', 'top_projects', 'hits', 'items'):
            items = data.get(key, [])
            if items:
                for p in items:
                    parsed = self._parse_json_project(p, is_top=(key == 'top_projects'))
                    if parsed:
                        projects.append(parsed)
                break
        return projects

    def _parse_json_project(self, p, is_top=False):
        """Convert a raw JSON project object into the internal dict format."""
        try:
            title = p.get('title', 'N/A')
            slug = p.get('slug', '')
            plink = p.get('plink', p.get('url', ''))

            if plink:
                link = f"{self.base_url}{plink}" if plink.startswith('/') else plink
            elif slug:
                link = f"{self.base_url}/projekte/{slug}"
            else:
                link = 'N/A'

            poster = p.get('poster', {})
            company = p.get('company') or poster.get('company', 'N/A') or 'N/A'

            raw_desc = p.get('description', '')
            description = BeautifulSoup(raw_desc, 'html.parser').get_text(strip=True) if raw_desc else 'N/A'

            matching = p.get('matching', {})
            kw_list = matching.get('keywordsLocalized', [])
            # Also try top-level fields
            if not kw_list:
                kw_list = p.get('keywords', [])
            keywords = ', '.join(kw_list) if kw_list else 'N/A'

            created_raw = p.get('created', '')
            try:
                dt = datetime.fromisoformat(created_raw.replace('Z', '+00:00'))
                created_date = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                created_date = created_raw or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            is_endcustomer = bool(p.get('endcustomer'))

            return {
                'titel': title,
                'link': link,
                'firma': company,
                'beschreibung': description,
                'keywords': keywords,
                'eintragungsdatum': created_date,
                'ist_top_projekt': is_top,
                'ist_endkundenprojekt': is_endcustomer,
            }
        except Exception as e:
            print(f"Fehler beim Parsen des JSON-Projekts: {e}")
            return None

    def _extract_from_html(self, soup):
        """Fallback: extract projects from server-rendered HTML after React hydration."""
        projects = []
        hit_list = soup.find('div', class_='hit-list')
        container = hit_list if hit_list else soup.find('body')
        if not container:
            return []

        seen_links = set()
        # Match individual project detail page URLs
        for a in container.find_all('a', href=True):
            href = a['href']
            if not re.search(r'/projekt(?:e)?[-/]', href):
                continue
            full_href = f"{self.base_url}{href}" if href.startswith('/') else href
            if full_href in seen_links:
                continue
            seen_links.add(full_href)

            # Walk up to find the enclosing project card
            card = a
            while card.parent and card.parent != container:
                card = card.parent

            data = self._extract_project_from_card(card, a, full_href)
            if data:
                projects.append(data)

        return projects

    def _extract_project_from_card(self, card, title_link, full_href):
        """Extract fields from a rendered project card element."""
        try:
            title = title_link.get_text(strip=True) or 'N/A'

            # Company: look for a link or element with 'company' in class
            company_elem = card.find(class_=re.compile(r'company', re.I))
            if not company_elem:
                company_elem = card.find('a', href=re.compile(r'/company|/firma'))
            company = company_elem.get_text(strip=True) if company_elem else 'N/A'

            # Keywords
            kw_elems = card.find_all(class_=re.compile(r'keyword|tag|skill|badge|label', re.I))
            keywords_list = list(dict.fromkeys(
                e.get_text(strip=True) for e in kw_elems if e.get_text(strip=True)
            ))
            keywords = ', '.join(keywords_list) if keywords_list else 'N/A'

            # Date
            date_elem = card.find(class_=re.compile(r'date|created|time', re.I))
            if not date_elem:
                date_elem = card.find('time')
            created_date = (
                date_elem.get('datetime') or date_elem.get_text(strip=True)
                if date_elem else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

            is_top = bool(card.find(class_=re.compile(r'top.?project|premium', re.I)))
            is_endcustomer = bool(card.find(class_=re.compile(r'endcustomer|endkunde', re.I)))

            return {
                'titel': title,
                'link': full_href,
                'firma': company,
                'beschreibung': 'N/A',
                'keywords': keywords,
                'eintragungsdatum': created_date,
                'ist_top_projekt': is_top,
                'ist_endkundenprojekt': is_endcustomer,
            }
        except Exception as e:
            print(f"Fehler beim Extrahieren der Karte: {e}")
            return None

    def scrape(self):
        try:
            if not self.login():
                return

            for page in range(1, self.max_pages + 1):
                projects = self.get_page(page)
                if not projects:
                    break

                for project in projects:
                    self.db.conn.execute("""
                        INSERT OR IGNORE INTO projects
                        (title, link, company, description, keywords,
                        created_date, is_top_project, is_endcustomer)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        project['titel'],
                        project['link'],
                        project['firma'],
                        project['beschreibung'],
                        project['keywords'],
                        project['eintragungsdatum'],
                        project['ist_top_projekt'],
                        project['ist_endkundenprojekt']
                    ))
                self.db.conn.commit()

                if page < self.max_pages:
                    time.sleep(random.uniform(2, 4))
        finally:
            self.close()


class ProjectMatcher:
    def __init__(self, db):
        self.db = db

    def find_matches(self, profile, min_score=30):
        projects = pd.read_sql_query("""
            SELECT * FROM projects
            WHERE created_date >= date('now', '-30 days')
        """, self.db.conn)

        matches = []
        for _, row in projects.iterrows():
            score, debug = self.calculate_match_score(row, profile)
            if score >= min_score:
                matches.append({
                    'project_id': row['id'],
                    'title': row['title'],
                    'link': row['link'],
                    'company': row['company'],
                    'description': row['description'],
                    'keywords': row['keywords'],
                    'created_date': row['created_date'],
                    'is_top_project': row['is_top_project'],
                    'is_endcustomer': row['is_endcustomer'],
                    'match_score': score,
                    'match_debug': debug
                })

        for match in matches:
            self.db.conn.execute("""
                INSERT INTO matches (
                    project_id, title, link, company, description, keywords,
                    created_date, is_top_project, is_endcustomer,
                    match_score, match_debug
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match['project_id'], match['title'], match['link'],
                match['company'], match['description'], match['keywords'],
                match['created_date'], match['is_top_project'],
                match['is_endcustomer'], match['match_score'],
                match['match_debug']
            ))
        self.db.conn.commit()

    def calculate_match_score(self, row, profile):
        score = 0
        debug_info = []

        excluded = []
        if row['description']:
            excluded.extend([k for k in profile['excluded_keywords']
                            if k.lower() in row['description'].lower()])
        if row['keywords']:
            excluded.extend([k for k in profile['excluded_keywords']
                            if k.lower() in row['keywords'].lower()])
        if row['title']:
            excluded.extend([k for k in profile['excluded_keywords']
                            if k.lower() in row['title'].lower()])

        if excluded:
            debug_info.append(f"Ausgeschlossen wegen: {list(set(excluded))}")
            return 0, "\n".join(debug_info)

        if row['keywords'] and row['keywords'] != 'N/A':
            project_keywords = set(kw.strip().lower() for kw in row['keywords'].split(','))
            profile_skills = set(s.lower() for s in profile['skills'])

            exact_matches = project_keywords.intersection(profile_skills)
            exact_score = (len(exact_matches) / max(len(project_keywords), 1)) * 30

            partial_matches = set()
            for p_kw in project_keywords:
                for skill in profile_skills:
                    if p_kw != skill and (skill in p_kw or p_kw in skill):
                        partial_matches.add(p_kw)

            partial_score = (len(partial_matches) / max(len(project_keywords), 1)) * 20

            score += exact_score + partial_score
            debug_info.append(f"Exact Keyword Score: {exact_score:.2f}")
            debug_info.append(f"Partial Keyword Score: {partial_score:.2f}")
            debug_info.append(f"Exact Matches: {exact_matches}")
            debug_info.append(f"Partial Matches: {partial_matches}")

        if row['description']:
            desc_lower = row['description'].lower()

            matching_skills = [s.lower() for s in profile['skills'] if s.lower() in desc_lower]
            skill_score = min((len(matching_skills) * 4), 20)

            matching_preferred = [k.lower() for k in profile['preferred_keywords'] if k.lower() in desc_lower]
            preferred_score = min((len(matching_preferred) * 2), 10)

            score += skill_score + preferred_score
            debug_info.append(f"Description Skills Score: {skill_score}")
            debug_info.append(f"Description Preferred Score: {preferred_score}")
            debug_info.append(f"Skills in Description: {matching_skills}")
            debug_info.append(f"Preferred in Description: {matching_preferred}")

        try:
            created = datetime.strptime(row['created_date'], '%Y-%m-%d %H:%M:%S')
            days_old = (datetime.now() - created).days
            time_score = 20 * math.exp(-days_old / 15)
            score += time_score
            debug_info.append(f"Time Score: {time_score:.2f}")
            debug_info.append(f"Days Old: {days_old}")
        except Exception:
            pass

        return score, "\n".join(debug_info)

    def get_statistics(self):
        stats = pd.read_sql_query("""
            SELECT
                AVG(match_score) as avg_score,
                COUNT(*) as total_matches,
                MAX(m.match_date) as latest_match,
                MIN(p.created_date) as oldest_project,
                COUNT(DISTINCT p.company) as unique_companies
            FROM matches m
            JOIN projects p ON m.project_id = p.id
            WHERE m.match_date >= date('now', '-7 days')
        """, self.db.conn)
        return stats.to_dict('records')[0]

    def export_matches(self, min_score=30, export_path=None):
        if export_path is None:
            export_path = f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        matches_df = pd.read_sql_query("""
            SELECT
                p.title, p.company, p.keywords, p.description,
                p.created_date, p.link, p.is_top_project,
                p.is_endcustomer, m.match_score, m.match_debug
            FROM matches m
            JOIN projects p ON m.project_id = p.id
            WHERE m.match_score >= ?
            ORDER BY m.match_score DESC
        """, self.db.conn, params=[min_score])

        matches_df.to_csv(export_path, index=False, sep=';')
        return export_path


if __name__ == "__main__":
    db = FreelancermapDatabase()
    scraper = FreelancermapScraper(
        db=db,
        username=FREELANCERMAP_USERNAME,
        password=FREELANCERMAP_PASSWORD,
        max_pages=MAX_PAGES
    )
    scraper.scrape()

    matcher = ProjectMatcher(db)
    matcher.find_matches(PROFILE, min_score=MIN_SCORE)
    stats = matcher.get_statistics()

    print(f"Matches: {stats['total_matches']}")
    print(f"Durchschnitt Score: {stats['avg_score']:.2f}")

    matcher.export_matches(min_score=MIN_SCORE)

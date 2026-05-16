import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import time
import random
import math
from dotenv import load_dotenv
import os

load_dotenv()


# Credentials
FREELANCERMAP_USERNAME = os.getenv('FREELANCERMAP_USERNAME')
FREELANCERMAP_PASSWORD = os.getenv('FREELANCERMAP_PASSWORD')

# Scraping Settings
MAX_PAGES = 10
MIN_SCORE = 40

# Profile Settings
PROFILE = {
    'skills': [
        'Python', 'JavaScript', 'React', 'Vue', 'MySQL', 
        'HTML', 'CSS', 'PHP', 'GCP', 'AWS', 'Cloud', 
        'AI', 'Frontend', 'Vue.js', 'JS', 
    ],
    'preferred_keywords': [
        'Webentwicklung', 'Backend', 'Webdesign','Frontend', 'Fullstack', 
        'API', 'Wordpress', 'GCP', 'AWS', 'Cloud', 'AI', 'OpenAI'
    ],
    'excluded_keywords': ['SAP', 'Drupal']
}


class FreelancermapDatabase:
    def __init__(self, db_path="freelancermap.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def close(self):
        self.conn.close()
        
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
        """
        Initialisiert den Scraper mit Login-Daten
        
        Args:
            username (str): Benutzername für freelancermap.de
            password (str): Passwort für freelancermap.de
            max_pages (int): Anzahl der zu scrapenden Seiten
        """
        self.base_url = "https://www.freelancermap.de"
        self.login_url = f"{self.base_url}/login"
        self.username = username
        self.password = password
        self.max_pages = max_pages
        self.session = requests.Session()
        
        # Basis-Headers für alle Requests
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'de,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1',
            'Sec-GPC': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
    }

    def login(self):
        try:
            print("Starte Login-Prozess...")

            # Erst die Login-Seite abrufen
            print("Lade Login-Seite...")
            self.session.get(
                self.login_url,
                headers=self.headers
            )
            
            # Login-spezifische Headers
            login_headers = self.headers.copy()
            login_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': 'https://www.freelancermap.de/login',
                'Origin': 'https://www.freelancermap.de',
            })
            
            login_data = {
                'login': self.username,
                'password': self.password,
                '_remember_me': '1'
            }
            
            print("Führe Login durch...")
            login_response = self.session.post(
                self.login_url,
                data=login_data,
                headers=login_headers,
                allow_redirects=True
            )
            
            print(f"Login-Status: {login_response.status_code}")
            print(f"Response URL: {login_response.url}")
            
            print("\nCookies nach Login:")
            for cookie in self.session.cookies:
                print(f"- {cookie.name}: {cookie.value}")
                
            if login_response.status_code in [200, 302]:
                time.sleep(2)
                
                print("\nPrüfe Account-Seite...")
                
                # Account-Seite mit aktualisierten Headers abrufen
                account_headers = self.headers.copy()
                account_headers.update({
                    'Referer': 'https://www.freelancermap.de/login',
                    'Cache-Control': 'max-age=0'
                })
                
                account_page = self.session.get(
                    'https://www.freelancermap.de/mein_account.html',
                    headers=account_headers
                )
                
                print(f"Account-Seite Status: {account_page.status_code}")
                
                if account_page.status_code == 200:
                    if any(indicator in account_page.text for indicator in ['Mein Konto', 'Profil', 'Logout', 'Abmelden']):
                        print("Login erfolgreich!")
                        return True
                    else:
                        print("Login fehlgeschlagen: Keine Login-Indikatoren gefunden")
                else:
                    print(f"Zugriff auf Account-Seite fehlgeschlagen: {account_page.status_code}")
                    
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
            f"pagenr={page_number}"
        ]
        return f"{self.base_url}/project/search/ajax?{'&'.join(params)}"

    def get_page(self, page_number):
        import json as json_lib
        url = self.get_page_url(page_number)
        print(f"\nAbrufen von Seite {page_number}")
        print(f"URL: {url}")

        try:
            ajax_headers = self.headers.copy()
            ajax_headers.update({
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
            })
            response = self.session.get(url, headers=ajax_headers)
            print(f"Status Code: {response.status_code}")

            if response.status_code != 200:
                print(f"Fehler: Status Code {response.status_code}")
                return []

            data = response.json()

            # Login abgelaufen
            if isinstance(data, dict) and data.get('redirect'):
                print("Login-Session abgelaufen, versuche erneuten Login...")
                if self.login():
                    return self.get_page(page_number)
                return []

            projects = data if isinstance(data, list) else data.get('projects', data.get('hits', []))

            if not projects:
                print("Keine Projekte auf dieser Seite gefunden.")
                return []

            print(f"Gefundene Projekte: {len(projects)}")
            project_data = []
            for project in projects:
                parsed = self._parse_project_json(project)
                if parsed:
                    project_data.append(parsed)
                    print(f"Extrahiert: {parsed.get('titel', '')[:60]}...")

            return project_data

        except Exception as e:
            import traceback
            print(f"Fehler beim Laden der Seite {page_number}: {str(e)}")
            print(traceback.format_exc())
            return []

    def _parse_project_json(self, project):
        try:
            title = project.get('title', 'N/A')
            company = project.get('company', 'N/A')

            project_path = project.get('links', {}).get('project', '')
            link = f"{self.base_url}{project_path}" if project_path else 'N/A'

            desc_html = project.get('description', '')
            if desc_html:
                desc_soup = BeautifulSoup(desc_html, 'html.parser')
                description = desc_soup.get_text(separator=' ', strip=True)
            else:
                description = 'N/A'

            # API liefert keine Keywords — wir extrahieren sie aus der Beschreibung
            keywords = 'N/A'

            created_raw = project.get('created', '')
            try:
                created_dt = datetime.fromisoformat(created_raw)
                created_date = created_dt.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                created_date = created_raw or 'N/A'

            is_top = project.get('topProject') is not None
            is_endcustomer = bool(project.get('endcustomer', False))

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
            print(f"Fehler beim Parsen eines Projekts: {str(e)}")
            return None
    
    def scrape(self):
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

class ProjectMatcher:
    def __init__(self, db):
        self.db = db
        
    def find_matches(self, profile, min_score=30):
        cur = self.db.conn.execute("""
            SELECT * FROM projects
            WHERE created_date >= date('now', '-30 days')
        """)
        projects = cur.fetchall()

        matches = []
        for row in projects:
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
        
        # Ausschlusskriterien prüfen (zuerst!)
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

        # Keywords Match (50 Punkte)
        if row['keywords'] and row['keywords'] != 'N/A':
            project_keywords = set(kw.strip().lower() for kw in row['keywords'].split(','))
            profile_skills = set(s.lower() for s in profile['skills'])
            
            # Exakte Matches (30 Punkte)
            exact_matches = project_keywords.intersection(profile_skills)
            exact_score = (len(exact_matches) / max(len(project_keywords), 1)) * 30
            
            # Teilweise Matches (20 Punkte)
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

        # Beschreibungs-Match mit Gewichtung (30 Punkte)
        if row['description']:
            desc_lower = row['description'].lower()
            
            # Skills in Beschreibung (20 Punkte)
            matching_skills = [s.lower() for s in profile['skills'] if s.lower() in desc_lower]
            skill_score = min((len(matching_skills) * 4), 20)
            
            # Bevorzugte Keywords (10 Punkte)
            matching_preferred = [k.lower() for k in profile['preferred_keywords'] if k.lower() in desc_lower]
            preferred_score = min((len(matching_preferred) * 2), 10)
            
            score += skill_score + preferred_score
            debug_info.append(f"Description Skills Score: {skill_score}")
            debug_info.append(f"Description Preferred Score: {preferred_score}")
            debug_info.append(f"Skills in Description: {matching_skills}")
            debug_info.append(f"Preferred in Description: {matching_preferred}")

        # Aktualität (20 Punkte) - exponentieller Verfall
        try:
            created = datetime.strptime(row['created_date'], '%Y-%m-%d %H:%M:%S')
            days_old = (datetime.now() - created).days
            time_score = 20 * math.exp(-days_old/15)
        except (ValueError, TypeError):
            time_score = 0
            days_old = -1
        score += time_score
        debug_info.append(f"Time Score: {time_score:.2f}")
        debug_info.append(f"Days Old: {days_old}")

        return score, "\n".join(debug_info)

    def get_statistics(self):
        cur = self.db.conn.execute("""
            SELECT
                AVG(match_score) as avg_score,
                COUNT(*) as total_matches,
                MAX(m.match_date) as latest_match,
                MIN(p.created_date) as oldest_project,
                COUNT(DISTINCT p.company) as unique_companies
            FROM matches m
            JOIN projects p ON m.project_id = p.id
            WHERE m.match_date >= date('now', '-7 days')
        """)
        return dict(cur.fetchone())

    def export_matches(self, min_score=30, export_path=None):
        import csv
        if export_path is None:
            export_path = f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        cur = self.db.conn.execute("""
            SELECT
                p.title, p.company, p.keywords, p.description,
                p.created_date, p.link, p.is_top_project,
                p.is_endcustomer, m.match_score, m.match_debug
            FROM matches m
            JOIN projects p ON m.project_id = p.id
            WHERE m.match_score >= ?
            ORDER BY m.match_score DESC
        """, (min_score,))
        rows = cur.fetchall()

        with open(export_path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow([d[0] for d in cur.description])
            w.writerows(rows)

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
    print(f"Durchschnitt Score: {(stats['avg_score'] or 0):.2f}")
    
    matcher.export_matches(min_score=MIN_SCORE)
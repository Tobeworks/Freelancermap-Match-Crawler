import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
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
MAX_PAGES = 100
MIN_SCORE = 35

# Profile Settings
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
            
            # Standard-Headers für alle Requests
            self.headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'de,en-US;q=0.7,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'Origin': 'https://www.freelancermap.de',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'DNT': '1'
            }
            
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
                'Referer': 'https://www.freelancermap.de/login'
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
        """Generiert die URL für eine bestimmte Seite der Projektbörse"""
        params = [
            "projectContractTypes[0]=contracting",
            "remoteInPercent[0]=100",
            "countries[]=1",  # Deutschland
            "countries[]=2",  # Österreich
            "countries[]=3",  # Schweiz
            "sort=1",        # Neueste zuerst
            f"pagenr={page_number}"
        ]
        return f"{self.base_url}/projektboerse.html?{'&'.join(params)}"

    def get_page(self, page_number):
        """Lädt eine einzelne Seite und extrahiert die Projektdaten"""
        url = self.get_page_url(page_number)
        print(f"\nAbrufen von Seite {page_number}")
        print(f"URL: {url}")
        
        try:
            # Seite abrufen
            response = self.session.get(url, headers=self.headers)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Prüfe ob Login noch aktiv
                if "Bitte melden Sie sich an" in response.text:
                    print("Login-Session abgelaufen, versuche erneuten Login...")
                    if self.login():
                        return self.get_page(page_number)  # Seite erneut abrufen
                    return []
                
                # Suche nach Projekten
                projects = soup.find_all('div', class_='project-container')
                if not projects:
                    print("Keine Projekte auf dieser Seite gefunden!")
                    return []
                
                print(f"Gefundene Projekte auf Seite {page_number}: {len(projects)}")
                
                # Extrahiere Daten
                project_data = []
                for project in projects:
                    data = self._extract_project_data(project)
                    if data:
                        project_data.append(data)
                        print(f"Extrahiert: {data.get('titel', 'Kein Titel')[:50]}...")
                
                return project_data
            else:
                print(f"Fehler beim Abrufen der Seite: Status Code {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Fehler beim Laden der Seite {page_number}: {str(e)}")
            return []
            
    def _extract_project_data(self, project):
        try:
            # Titel und Link extrahieren
            title_elem = project.find('h2', class_='body')
            if title_elem:
                title_link = title_elem.find('a', class_='project-title')
                if title_link:
                    titel = title_link.get_text(strip=True)
                    link = f"https://www.freelancermap.de{title_link['href']}"
                    
                    # Detailseite aufrufen
                    detail_page = self.session.get(link, headers=self.headers)
                    if detail_page.status_code == 200:
                        detail_soup = BeautifulSoup(detail_page.text, 'html.parser')
                        desc_elem = detail_soup.find('div', {'data-translatable': 'description'})
                        if desc_elem:
                            description = desc_elem.get_text(strip=True)
                        else:
                            description = "N/A"
                        time.sleep(random.uniform(1, 2))
                    else:
                        description = "N/A"
                else:
                    titel = "N/A"
                    link = "N/A"
                    description = "N/A"
            else:
                titel = "N/A"
                link = "N/A" 
                description = "N/A"

            # Rest des Codes bleibt gleich...
            company_elem = project.find('a', class_='company')
            company = company_elem.get_text(strip=True) if company_elem else "N/A"
            
            keywords = []
            keywords_container = project.find('div', class_='keywords-container')
            if keywords_container:
                for keyword in keywords_container.find_all('span', class_='keyword'):
                    if 'tip_activator' not in keyword.get('class', []):
                        keywords.append(keyword.get_text(strip=True))
                
                tooltip = keywords_container.find('span', class_='tip_activator')
                if tooltip and 'data-tooltip-title' in tooltip.attrs:
                    tooltip_keywords = tooltip['data-tooltip-title'].split('\n')
                    keywords.extend([k.strip() for k in tooltip_keywords if k.strip()])
            
            date_elem = project.find('span', class_='created-date')
            if date_elem:
                date_text = date_elem.get_text(strip=True).replace('eingetragen am:', '').strip()
                try:
                    date_parts = date_text.split('/')
                    date_str = date_parts[0].strip()
                    time_str = date_parts[1].strip()
                    
                    day, month, year = date_str.split('.')
                    hour, minute = time_str.split(':')
                    
                    created_date = f"{year}-{month.zfill(2)}-{day.zfill(2)} {hour.zfill(2)}:{minute.zfill(2)}:00"
                except:
                    created_date = date_text
            else:
                created_date = "N/A"
            
            is_top = bool(project.find('div', class_='top-project-badge'))
            is_endkunde = bool(project.find('div', class_='endcustomer-badge'))
            
            data = {
                'titel': titel,
                'link': link,
                'firma': company,
                'beschreibung': description,
                'keywords': ', '.join(keywords) if keywords else "N/A",
                'eintragungsdatum': created_date,
                'ist_top_projekt': is_top,
                'ist_endkundenprojekt': is_endkunde
            }
            
            return data
            
        except Exception as e:
            print(f"Fehler beim Extrahieren der Projektdaten: {str(e)}")
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
        created = datetime.strptime(row['created_date'], '%Y-%m-%d %H:%M:%S')
        days_old = (datetime.now() - created).days
        time_score = 20 * math.exp(-days_old/15)  # Exponentieller Verfall über 15 Tage
        score += time_score
        debug_info.append(f"Time Score: {time_score:.2f}")
        debug_info.append(f"Days Old: {days_old}")

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
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import random

class FreelancermapScraper:
    def __init__(self, username, password, max_pages=2):
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
        """Extrahiert die relevanten Daten aus einem Projekt-Element"""
        try:
            # Titel und Link
            title_elem = project.find('h2', class_='body')
            if title_elem:
                title_link = title_elem.find('a', class_='project-title')
                if title_link:
                    titel = title_link.get_text(strip=True)
                    link = f"https://www.freelancermap.de{title_link['href']}"
                else:
                    titel = "N/A"
                    link = "N/A"
            else:
                titel = "N/A"
                link = "N/A"
            
            # Firmenname
            company_elem = project.find('a', class_='company')
            company = company_elem.get_text(strip=True) if company_elem else "N/A"
            
            # Beschreibung
            description_elem = project.find('div', class_='project-description') or \
                             project.find('div', class_='description')
            if description_elem:
                weniger_link = description_elem.find('a')
                if weniger_link:
                    weniger_link.decompose()
                description = description_elem.get_text(strip=True)
                description = ' '.join(description.split())
            else:
                description = "N/A"
            
            # Keywords
            keywords = []
            keywords_container = project.find('div', class_='keywords-container')
            if keywords_container:
                for keyword in keywords_container.find_all('span', class_='keyword'):
                    if 'tip_activator' not in keyword.get('class', []):
                        keywords.append(keyword.get_text(strip=True))
                
                # Tooltip Keywords
                tooltip = keywords_container.find('span', class_='tip_activator')
                if tooltip and 'data-tooltip-title' in tooltip.attrs:
                    tooltip_keywords = tooltip['data-tooltip-title'].split('\n')
                    keywords.extend([k.strip() for k in tooltip_keywords if k.strip()])
            
            # Eintragungsdatum
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
            
            # Status
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
        """Hauptmethode zum Scrapen aller Seiten"""
        # Zuerst einloggen
        if not self.login():
            print("Scraping wird abgebrochen, da Login fehlgeschlagen.")
            return pd.DataFrame()
            
        print("\nStarte Scraping...")
        all_projects = []
        unique_links = set()
        
        for page in range(1, self.max_pages + 1):
            print(f"\n{'='*50}")
            print(f"Scrape Seite {page}...")
            print(f"{'='*50}")
            
            projects = self.get_page(page)
            if not projects:
                print(f"Keine weiteren Projekte auf Seite {page}. Beende Scraping.")
                break
                
            # Füge nur neue Projekte hinzu
            for project in projects:
                if project['link'] not in unique_links:
                    unique_links.add(project['link'])
                    all_projects.append(project)
            
            print(f"Unique Projekte bisher: {len(unique_links)}")
            
            # Pause zwischen Seiten
            if page < self.max_pages:
                delay = random.uniform(2, 4)
                print(f"Warte {delay:.2f} Sekunden...")
                time.sleep(delay)
        
        # Erstelle DataFrame
        df = pd.DataFrame(all_projects)
        
        if not df.empty:
            # Sortiere nach Datum
            df['eintragungsdatum'] = pd.to_datetime(df['eintragungsdatum'], errors='coerce')
            df = df.sort_values('eintragungsdatum', ascending=False)
            
            # Speichere CSV
            filename = 'freelancermap_projekte.csv'
            df.to_csv(filename, index=False, encoding='utf-8')
            print(f"\nDaten wurden in {filename} gespeichert.")
            
            # Statistiken
            print("\nStatistiken:")
            print(f"Gesamtanzahl unique Projekte: {len(df)}")
            print(f"Top-Projekte: {df['ist_top_projekt'].sum()}")
            print(f"Endkundenprojekte: {df['ist_endkundenprojekt'].sum()}")
            
            print("\nTop 5 Firmen:")
            print(df['firma'].value_counts().head())
            
        return df

# Beispiel für die Verwendung:
if __name__ == "__main__":
    # Hier Ihre Login-Daten einfügen
    username = ""
    password = ""
    
    # Scraper initialisieren und ausführen
    scraper = FreelancermapScraper(
        username=username,
        password=password,
        max_pages=3
    )
    projects_df = scraper.scrape()
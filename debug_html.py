#!/usr/bin/env python3
"""
Debug-Skript: Lädt die Projektliste und speichert HTML + Selektor-Diagnose.
Ausführen: python3 debug_html.py
"""
import os, time, sys
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv()
USERNAME = os.getenv('FREELANCERMAP_USERNAME')
PASSWORD = os.getenv('FREELANCERMAP_PASSWORD')

if not USERNAME or not PASSWORD:
    print("FEHLER: Bitte FREELANCERMAP_USERNAME und FREELANCERMAP_PASSWORD in .env setzen.")
    sys.exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'de,en-US;q=0.7,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
}

session = requests.Session()

# Login
print("Login läuft...")
session.get('https://www.freelancermap.de/login', headers=HEADERS)
login_headers = {**HEADERS, 'Content-Type': 'application/x-www-form-urlencoded',
                 'Referer': 'https://www.freelancermap.de/login', 'Origin': 'https://www.freelancermap.de'}
r = session.post('https://www.freelancermap.de/login',
                 data={'login': USERNAME, 'password': PASSWORD, '_remember_me': '1'},
                 headers=login_headers, allow_redirects=True)
print(f"  Status: {r.status_code}, URL: {r.url}")

time.sleep(2)
acc = session.get('https://www.freelancermap.de/mein_account.html', headers=HEADERS)
if not any(x in acc.text for x in ['Mein Konto', 'Profil', 'Logout', 'Abmelden']):
    print("FEHLER: Login fehlgeschlagen.")
    sys.exit(1)
print("Login OK.\n")

# Seite laden
url = ('https://www.freelancermap.de/projektboerse.html'
       '?projectContractTypes[0]=contracting&remoteInPercent[0]=100'
       '&countries[]=1&countries[]=2&countries[]=3&sort=1&pagenr=1')
print(f"Lade: {url}")
resp = session.get(url, headers=HEADERS)
print(f"Status: {resp.status_code}\n")

html = resp.text

# HTML speichern
with open('debug_page.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("HTML gespeichert: debug_page.html\n")

soup = BeautifulSoup(html, 'html.parser')

# Selektor-Diagnose
candidates = [
    ('div', 'project-container'),
    ('div', 'project-item'),
    ('div', 'project'),
    ('article', None),
    ('li', 'project'),
    ('div', 'card'),
    ('div', 'project-card'),
    ('div', 'list-item'),
    ('div', 'tile'),
]

print("=== Selektor-Diagnose ===")
for tag, cls in candidates:
    if cls:
        els = soup.find_all(tag, class_=cls)
    else:
        els = soup.find_all(tag)
    if els:
        print(f"  GEFUNDEN  <{tag} class='{cls}'>  →  {len(els)} Elemente")
        # Erstes Element zeigen
        first = els[0]
        print(f"    Klassen: {first.get('class')}")
        print(f"    Text-Anfang: {first.get_text(strip=True)[:120]}")
    else:
        print(f"  leer      <{tag} class='{cls}'>")

# Alle divs mit 'project' im Klassennamen finden
print("\n=== Alle divs mit 'project' im Klassennamen ===")
for div in soup.find_all('div'):
    classes = div.get('class', [])
    if any('project' in c.lower() for c in classes):
        print(f"  {classes}  →  {div.get_text(strip=True)[:80]}")

# Alle article-Tags
articles = soup.find_all('article')
print(f"\n=== article-Tags gesamt: {len(articles)} ===")
if articles:
    for a in articles[:3]:
        print(f"  Klassen: {a.get('class')}  →  {a.get_text(strip=True)[:100]}")

print("\nFertig. Bitte debug_page.html prüfen wenn die Ausgabe oben unklar ist.")

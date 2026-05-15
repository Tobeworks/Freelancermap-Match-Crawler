#!/usr/bin/env python3
"""
Freelancermap Match Crawler – Desktop UI
Requires: pip install PyQt6
Cross-platform: macOS, Windows, Linux
"""

import os
import sys
import json
import csv
import re
import threading
import queue
import sqlite3
import webbrowser
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSortFilterProxyModel
from PyQt6.QtGui import QFont, QColor, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QTextEdit,
    QTableView, QHeaderView, QProgressBar, QFileDialog,
    QMessageBox, QGroupBox, QCheckBox, QStatusBar, QSplitter,
    QAbstractItemView, QComboBox,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, '.env')
UI_CONFIG_FILE = os.path.join(BASE_DIR, 'ui_config.json')

DEFAULT_CONFIG = {
    'username': '',
    'password': '',
    'max_pages': 10,
    'min_score': 35,
    'matching_enabled': True,
    'skills': 'Python, JavaScript, React, Vue, MySQL, HTML, CSS, PHP, GCP, AWS, Cloud, AI, Frontend, Vue.js, JS',
    'preferred_keywords': 'Webentwicklung, Backend, Frontend, Fullstack, API, Wordpress, GCP, AWS, Cloud, AI, OpenAI',
    'excluded_keywords': 'SAP, Drupal',
    'search_query': '',
    'categories': [1],
    'countries': [1, 2, 3],
    'remote_percent': 100,
    'contract_types': ['contracting'],
    'endcustomer_only': False,
    'sort': 1,
    'direct_url': '',
}

_CATEGORIES = [
    (1,  'Web- & Softwareentwicklung'),
    (2,  'Schreiben & Übersetzen'),
    (3,  'Grafikdesign & Kreativdienste'),
    (4,  'Digitales Marketing'),
    (6,  'Ingenieurwesen'),
    (7,  'Finanz- & Rechnungswesen'),
    (8,  'Management & Beratung'),
    (9,  'Forschung & Analyse'),
    (11, 'IT-Dienstleistungen'),
]

_COUNTRIES = [
    (1, 'Deutschland'),
    (2, 'Österreich'),
    (3, 'Schweiz'),
]

_CONTRACT_TYPES = [
    ('contracting',        'Freiberuflich'),
    ('permanent_position', 'Festanstellung'),
    ('employee_leasing',   'Arbeitnehmerüberlassung'),
]

_REMOTE_OPTIONS = [
    ('Alle (kein Filter)', None),
    ('100% Remote',        100),
    ('≥ 90% Remote',        90),
    ('≥ 80% Remote',        80),
    ('≥ 60% Remote',        60),
    ('≥ 40% Remote',        40),
    ('≥ 20% Remote',        20),
    ('Vor Ort (0%)',          0),
]

_SORT_OPTIONS = [
    ('Neueste zuerst',  1),
    ('Relevanz',        2),
]


def parse_freelancermap_url(url):
    """Parse a freelancermap search URL into filter parameter dict.

    Returns a dict with recognized keys (categories, contract_types,
    remote_percent, countries, sort) and 'matching_skills_count' for
    information purposes.  Unknown/unparseable values are silently ignored.
    """
    try:
        parsed = urlparse(url.strip())
        params = parse_qs(parsed.query, keep_blank_values=False)
    except Exception:
        return {}

    result = {}

    cats = []
    for key, vals in params.items():
        if re.match(r'categories\[', key):
            for v in vals:
                try:
                    cats.append(int(v))
                except ValueError:
                    pass
    if cats:
        result['categories'] = cats

    cts = []
    for key, vals in params.items():
        if re.match(r'projectContractTypes\[', key):
            cts.extend(vals)
    if cts:
        result['contract_types'] = cts

    for key, vals in params.items():
        if re.match(r'remoteInPercent\[', key):
            try:
                result['remote_percent'] = int(vals[0])
            except (ValueError, IndexError):
                pass

    countries = []
    for key, vals in params.items():
        if re.match(r'countries', key):
            for v in vals:
                try:
                    countries.append(int(v))
                except ValueError:
                    pass
    if countries:
        result['countries'] = countries

    if 'sort' in params:
        try:
            result['sort'] = int(params['sort'][0])
        except (ValueError, IndexError):
            pass

    result['matching_skills_count'] = sum(
        1 for k in params if re.match(r'matchingSkills\[', k)
    )
    return result


def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    value = value.strip().strip('"').strip("'")
                    if key.strip() == 'FREELANCERMAP_USERNAME':
                        config['username'] = value
                    elif key.strip() == 'FREELANCERMAP_PASSWORD':
                        config['password'] = value
    if os.path.exists(UI_CONFIG_FILE):
        with open(UI_CONFIG_FILE, encoding='utf-8') as f:
            config.update(json.load(f))
    return config


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"FREELANCERMAP_USERNAME={config['username']}\n")
        f.write(f"FREELANCERMAP_PASSWORD={config['password']}\n")
    extra = {k: v for k, v in config.items() if k not in ('username', 'password')}
    with open(UI_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(extra, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ Worker

class ScraperWorker(QThread):
    log = pyqtSignal(str, str)   # message, level
    finished = pyqtSignal(int)   # match count

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import importlib, sys, traceback, time, random

        class Capture:
            def __init__(self, sig, level):
                self.sig = sig
                self.level = level
                self.buf = ''
            def write(self, text):
                self.buf += text
                while '\n' in self.buf:
                    line, self.buf = self.buf.split('\n', 1)
                    if line.strip():
                        self.sig.emit(line, self.level)
            def flush(self):
                if self.buf.strip():
                    self.sig.emit(self.buf, self.level)
                    self.buf = ''

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = Capture(self.log, 'info')
        sys.stderr = Capture(self.log, 'error')

        try:
            import projectMatcher
            importlib.reload(projectMatcher)

            profile = {
                'skills':             [s.strip() for s in self.config['skills'].split(',') if s.strip()],
                'preferred_keywords': [s.strip() for s in self.config['preferred_keywords'].split(',') if s.strip()],
                'excluded_keywords':  [s.strip() for s in self.config['excluded_keywords'].split(',') if s.strip()],
            }
            max_pages = max(1, int(self.config['max_pages']))
            min_score = int(self.config['min_score'])

            direct_url = self.config.get('direct_url', '').strip()
            search_config = {
                'search_query':   self.config.get('search_query', ''),
                'categories':     self.config.get('categories', [1]),
                'countries':      self.config.get('countries', [1, 2, 3]),
                'remote_percent': self.config.get('remote_percent', 100),
                'contract_types': self.config.get('contract_types', ['contracting']),
                'endcustomer_only': self.config.get('endcustomer_only', False),
                'sort':           self.config.get('sort', 1),
                'direct_url':     direct_url,
            }

            self.log.emit(f'Starte Scraping  |  Seiten: {max_pages}  |  Min-Score: {min_score}', 'info')
            self.log.emit(f'Skills: {", ".join(profile["skills"][:8])} …', 'info')
            if direct_url:
                self.log.emit(f'Modus: URL-Import  |  pagenr wird pro Seite angepasst', 'info')
                self.log.emit(f'URL: {direct_url[:80]}{"…" if len(direct_url) > 80 else ""}', 'info')
            else:
                query_hint = search_config['search_query'] or '(alle)'
                self.log.emit(f'Suchbegriff: {query_hint}  |  Remote: {search_config["remote_percent"]}%', 'info')

            db = projectMatcher.FreelancermapDatabase()
            scraper = projectMatcher.FreelancermapScraper(
                db=db,
                username=self.config['username'],
                password=self.config['password'],
                max_pages=max_pages,
                search_config=search_config,
            )

            if not scraper.login():
                self.log.emit('Login fehlgeschlagen – Zugangsdaten prüfen.', 'error')
                self.finished.emit(0)
                return

            scraped = 0
            for page in range(1, max_pages + 1):
                if self._stop:
                    self.log.emit('Scraping gestoppt.', 'warning')
                    break
                projects = scraper.get_page(page)
                if not projects:
                    self.log.emit(f'Seite {page}: keine Projekte mehr.', 'warning')
                    break
                for p in projects:
                    db.conn.execute(
                        'INSERT OR IGNORE INTO projects '
                        '(title, link, company, description, keywords, '
                        'created_date, is_top_project, is_endcustomer) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (p['titel'], p['link'], p['firma'], p['beschreibung'],
                         p['keywords'], p['eintragungsdatum'],
                         p['ist_top_projekt'], p['ist_endkundenprojekt']),
                    )
                    scraped += 1
                db.conn.commit()
                self.log.emit(f'Seite {page}: {len(projects)} Projekte ({scraped} gesamt)', 'info')
                if page < max_pages and not self._stop:
                    time.sleep(random.uniform(2, 4))

            if not self._stop:
                matching_enabled = self.config.get('matching_enabled', True)
                if matching_enabled:
                    self.log.emit(f'{scraped} Projekte gespeichert. Starte Matching …', 'success')
                    matcher = projectMatcher.ProjectMatcher(db)
                    matcher.find_matches(profile, min_score=min_score)
                    try:
                        stats = matcher.get_statistics()
                        total = stats.get('total_matches', 0)
                        avg   = stats.get('avg_score') or 0
                        self.log.emit(f'Fertig!  Matches: {total}  |  Ø Score: {avg:.1f}', 'success')
                        self.finished.emit(total)
                        return
                    except Exception:
                        pass
                else:
                    self.log.emit(
                        f'{scraped} Projekte gespeichert. Matching deaktiviert – alle Projekte extrahiert.',
                        'success')
                    self.finished.emit(scraped)
                    return
            self.finished.emit(0)

        except Exception as exc:
            self.log.emit(f'Fehler: {exc}', 'error')
            self.log.emit(traceback.format_exc(), 'error')
            self.finished.emit(0)
        finally:
            sys.stdout = old_out
            sys.stderr = old_err


# -------------------------------------------------------------- Main Window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Freelancermap Match Crawler')
        self.resize(1080, 740)
        self.config = load_config()
        self._matches = []
        self._worker = None

        tabs = QTabWidget()
        tabs.addTab(self._build_config_tab(),     '  Konfiguration  ')
        tabs.addTab(self._build_crawler_tab(),    '  Crawler  ')
        tabs.addTab(self._build_matches_tab(),    '  Matches  ')
        tabs.addTab(self._build_statistics_tab(), '  Statistiken  ')
        self.setCentralWidget(tabs)
        self._tabs = tabs

        self.statusBar().showMessage('Bereit')

    # --------------------------------------------------------- Config tab

    def _build_config_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setSpacing(12)

        # Credentials
        cred = QGroupBox('Anmeldedaten (freelancermap.de)')
        fl = QFormLayout(cred)
        fl.setSpacing(8)
        self._username = QLineEdit(self.config['username'])
        self._username.setPlaceholderText('ihre@email.de')
        self._password = QLineEdit(self.config['password'])
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        show_pw = QCheckBox('Passwort anzeigen')
        show_pw.toggled.connect(
            lambda on: self._password.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        fl.addRow('E-Mail:', self._username)
        fl.addRow('Passwort:', self._password)
        fl.addRow('', show_pw)
        root.addWidget(cred)

        # Scraper settings
        sc = QGroupBox('Scraper-Einstellungen')
        fl2 = QFormLayout(sc)
        fl2.setSpacing(8)
        self._max_pages = QSpinBox()
        self._max_pages.setRange(1, 200)
        self._max_pages.setValue(int(self.config['max_pages']))
        self._max_pages.setFixedWidth(80)
        self._min_score = QSpinBox()
        self._min_score.setRange(0, 100)
        self._min_score.setValue(int(self.config['min_score']))
        self._min_score.setFixedWidth(80)
        self._matching_enabled = QCheckBox('Profil-Matching aktivieren')
        self._matching_enabled.setChecked(self.config.get('matching_enabled', True))
        self._matching_enabled.setToolTip(
            'Wenn deaktiviert, werden alle Projekte ohne Matching gespeichert '
            '(nützlich für reine Extraktion aller Ergebnisse).')
        fl2.addRow('Max. Seiten:', self._max_pages)
        fl2.addRow('Min. Score (0–100):', self._min_score)
        fl2.addRow('Matching:', self._matching_enabled)
        root.addWidget(sc)

        # Profile
        pr = QGroupBox('Profil (Matching)')
        fl3 = QFormLayout(pr)
        fl3.setSpacing(8)
        self._skills    = QLineEdit(self.config['skills'])
        self._preferred = QLineEdit(self.config['preferred_keywords'])
        self._excluded  = QLineEdit(self.config['excluded_keywords'])
        fl3.addRow('Skills (kommagetrennt):', self._skills)
        fl3.addRow('Bevorzugte Keywords:', self._preferred)
        fl3.addRow('Ausgeschlossene Keywords:', self._excluded)
        root.addWidget(pr)

        # Search Filters
        sf = QGroupBox('Suchfilter (Playwright)')
        sf_vl = QVBoxLayout(sf)
        sf_vl.setSpacing(8)

        # --- URL Import ---
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel('Freelancermap-Link:'))
        self._direct_url = QLineEdit(self.config.get('direct_url', ''))
        self._direct_url.setPlaceholderText(
            'Suchlink von freelancermap.de hier einfügen und auf „Importieren" klicken …')
        url_row.addWidget(self._direct_url)
        import_btn = QPushButton('Importieren')
        import_btn.setFixedWidth(110)
        import_btn.clicked.connect(self._import_url)
        url_row.addWidget(import_btn)
        clear_url_btn = QPushButton('Löschen')
        clear_url_btn.setFixedWidth(80)
        clear_url_btn.clicked.connect(self._clear_url)
        url_row.addWidget(clear_url_btn)
        sf_vl.addLayout(url_row)

        self._url_status = QLabel('')
        self._url_status.setStyleSheet('color: #4ec9b0; font-style: italic;')
        if self.config.get('direct_url', ''):
            self._url_status.setText('URL aktiv – Filter werden beim Scraping von der URL übernommen.')
        sf_vl.addWidget(self._url_status)

        # Search query
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel('Suchbegriff:'))
        self._search_query = QLineEdit(self.config.get('search_query', ''))
        self._search_query.setPlaceholderText('z.B. Python Developer  (leer = alle Projekte)')
        q_row.addWidget(self._search_query)
        sf_vl.addLayout(q_row)

        # Categories
        sf_vl.addWidget(QLabel('Kategorien:'))
        cat_grid = QGridLayout()
        cat_grid.setSpacing(4)
        self._category_checks = {}
        selected_cats = self.config.get('categories', [1])
        for idx, (cat_id, cat_name) in enumerate(_CATEGORIES):
            cb = QCheckBox(cat_name)
            cb.setChecked(cat_id in selected_cats)
            self._category_checks[cat_id] = cb
            cat_grid.addWidget(cb, idx // 3, idx % 3)
        sf_vl.addLayout(cat_grid)

        # Countries
        sf_vl.addWidget(QLabel('Länder:'))
        c_row = QHBoxLayout()
        self._country_checks = {}
        selected_countries = self.config.get('countries', [1, 2, 3])
        for c_id, c_name in _COUNTRIES:
            cb = QCheckBox(c_name)
            cb.setChecked(c_id in selected_countries)
            self._country_checks[c_id] = cb
            c_row.addWidget(cb)
        c_row.addStretch()
        sf_vl.addLayout(c_row)

        # Contract types
        sf_vl.addWidget(QLabel('Vertragstypen:'))
        ct_row = QHBoxLayout()
        self._contract_checks = {}
        selected_cts = self.config.get('contract_types', ['contracting'])
        for ct_val, ct_name in _CONTRACT_TYPES:
            cb = QCheckBox(ct_name)
            cb.setChecked(ct_val in selected_cts)
            self._contract_checks[ct_val] = cb
            ct_row.addWidget(cb)
        ct_row.addStretch()
        sf_vl.addLayout(ct_row)

        # Remote + Endcustomer + Sort
        misc_row = QHBoxLayout()
        misc_row.addWidget(QLabel('Remote:'))
        self._remote_combo = QComboBox()
        self._remote_values = [v for _, v in _REMOTE_OPTIONS]
        current_remote = self.config.get('remote_percent', 100)
        for label, _ in _REMOTE_OPTIONS:
            self._remote_combo.addItem(label)
        if current_remote in self._remote_values:
            self._remote_combo.setCurrentIndex(self._remote_values.index(current_remote))
        self._remote_combo.setFixedWidth(160)
        misc_row.addWidget(self._remote_combo)

        misc_row.addSpacing(20)
        misc_row.addWidget(QLabel('Sortierung:'))
        self._sort_combo = QComboBox()
        self._sort_values = [v for _, v in _SORT_OPTIONS]
        current_sort = self.config.get('sort', 1)
        for label, _ in _SORT_OPTIONS:
            self._sort_combo.addItem(label)
        if current_sort in self._sort_values:
            self._sort_combo.setCurrentIndex(self._sort_values.index(current_sort))
        self._sort_combo.setFixedWidth(160)
        misc_row.addWidget(self._sort_combo)

        misc_row.addSpacing(20)
        self._endcustomer_check = QCheckBox('Nur Endkunden-Projekte')
        self._endcustomer_check.setChecked(self.config.get('endcustomer_only', False))
        misc_row.addWidget(self._endcustomer_check)
        misc_row.addStretch()
        sf_vl.addLayout(misc_row)

        root.addWidget(sf)

        root.addStretch()
        btn = QPushButton('Einstellungen speichern')
        btn.clicked.connect(self._save_config)
        hl = QHBoxLayout()
        hl.addStretch()
        hl.addWidget(btn)
        root.addLayout(hl)
        return w

    def _save_config(self):
        cats     = [cid for cid, cb in self._category_checks.items() if cb.isChecked()]
        countries = [cid for cid, cb in self._country_checks.items() if cb.isChecked()]
        cts      = [val for val, cb in self._contract_checks.items() if cb.isChecked()]
        remote   = self._remote_values[self._remote_combo.currentIndex()]
        sort_val = self._sort_values[self._sort_combo.currentIndex()]

        self.config.update({
            'username':           self._username.text(),
            'password':           self._password.text(),
            'max_pages':          self._max_pages.value(),
            'min_score':          self._min_score.value(),
            'matching_enabled':   self._matching_enabled.isChecked(),
            'skills':             self._skills.text(),
            'preferred_keywords': self._preferred.text(),
            'excluded_keywords':  self._excluded.text(),
            'search_query':       self._search_query.text().strip(),
            'categories':         cats,
            'countries':          countries,
            'remote_percent':     remote,
            'contract_types':     cts,
            'endcustomer_only':   self._endcustomer_check.isChecked(),
            'sort':               sort_val,
            'direct_url':         self._direct_url.text().strip(),
        })
        save_config(self.config)
        self.statusBar().showMessage('Einstellungen gespeichert.')

    def _import_url(self):
        url = self._direct_url.text().strip()
        if not url:
            self._url_status.setStyleSheet('color: #f44747; font-style: italic;')
            self._url_status.setText('Bitte zuerst einen Freelancermap-Link einfügen.')
            return

        if 'freelancermap.de' not in url:
            self._url_status.setStyleSheet('color: #f44747; font-style: italic;')
            self._url_status.setText('Ungültige URL – bitte einen freelancermap.de-Link verwenden.')
            return

        parsed = parse_freelancermap_url(url)
        if not parsed:
            self._url_status.setStyleSheet('color: #f44747; font-style: italic;')
            self._url_status.setText('URL konnte nicht geparst werden.')
            return

        # Update category checkboxes
        if 'categories' in parsed:
            for cat_id, cb in self._category_checks.items():
                cb.setChecked(cat_id in parsed['categories'])

        # Update country checkboxes
        if 'countries' in parsed:
            for c_id, cb in self._country_checks.items():
                cb.setChecked(c_id in parsed['countries'])

        # Update contract type checkboxes
        if 'contract_types' in parsed:
            for ct_val, cb in self._contract_checks.items():
                cb.setChecked(ct_val in parsed['contract_types'])

        # Update remote combo
        if 'remote_percent' in parsed:
            remote = parsed['remote_percent']
            if remote in self._remote_values:
                self._remote_combo.setCurrentIndex(self._remote_values.index(remote))

        # Update sort combo
        if 'sort' in parsed:
            sort_val = parsed['sort']
            if sort_val in self._sort_values:
                self._sort_combo.setCurrentIndex(self._sort_values.index(sort_val))

        # Build status summary
        parts = []
        if parsed.get('matching_skills_count'):
            parts.append(f"{parsed['matching_skills_count']} Skills")
        if 'categories' in parsed:
            parts.append(f"Kategorien: {parsed['categories']}")
        if 'remote_percent' in parsed:
            parts.append(f"{parsed['remote_percent']}% Remote")
        if 'countries' in parsed:
            parts.append(f"Länder: {parsed['countries']}")

        summary = ' · '.join(parts) if parts else 'Parameter importiert'
        self._url_status.setStyleSheet('color: #4ec9b0; font-style: italic;')
        self._url_status.setText(f'URL aktiv – {summary}')
        self.statusBar().showMessage('URL importiert.')

    def _clear_url(self):
        self._direct_url.clear()
        self._url_status.setText('')
        self.statusBar().showMessage('URL-Filter gelöscht – manuelle Filter aktiv.')

    # -------------------------------------------------------- Crawler tab

    def _build_crawler_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)

        # Buttons
        hl = QHBoxLayout()
        self._start_btn = QPushButton('▶  Scraping starten')
        self._start_btn.setFixedHeight(34)
        font = self._start_btn.font()
        font.setBold(True)
        self._start_btn.setFont(font)
        self._start_btn.clicked.connect(self._start_scraping)

        self._stop_btn = QPushButton('■  Stoppen')
        self._stop_btn.setFixedHeight(34)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_scraping)

        clear_btn = QPushButton('Log leeren')
        clear_btn.clicked.connect(lambda: self._log_view.clear())

        hl.addWidget(self._start_btn)
        hl.addWidget(self._stop_btn)
        hl.addWidget(clear_btn)
        hl.addStretch()
        vl.addLayout(hl)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        vl.addWidget(self._progress)

        # Log
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont('Menlo' if sys.platform == 'darwin' else 'Courier New', 10))
        self._log_view.setStyleSheet(
            'QTextEdit { background:#1e1e1e; color:#d4d4d4; border:none; }')
        vl.addWidget(self._log_view)
        return w

    def _start_scraping(self):
        if not self._username.text() or not self._password.text():
            QMessageBox.warning(self, 'Fehler',
                                'Bitte E-Mail und Passwort in der Konfiguration eintragen.')
            self._tabs.setCurrentIndex(0)
            return
        self._save_config()
        self._worker = ScraperWorker(self.config)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._scraping_done)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setVisible(True)
        self.statusBar().showMessage('Scraping läuft …')
        self._worker.start()

    def _stop_scraping(self):
        if self._worker:
            self._worker.stop()
        self._append_log('Stopp-Signal gesendet …', 'warning')

    def _scraping_done(self, count):
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setVisible(False)
        msg = f'Fertig – {count} Matches gefunden.' if count else 'Abgeschlossen.'
        self.statusBar().showMessage(msg)

    def _append_log(self, message, level):
        colors = {
            'info':    '#d4d4d4',
            'success': '#4ec9b0',
            'error':   '#f44747',
            'warning': '#dcdcaa',
        }
        ts    = datetime.now().strftime('%H:%M:%S')
        color = colors.get(level, '#d4d4d4')
        html  = (
            f'<span style="color:#858585">[{ts}]</span> '
            f'<span style="color:{color}">{message}</span>'
        )
        self._log_view.append(html)

    # -------------------------------------------------------- Matches tab

    def _build_matches_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)

        # Toolbar
        hl = QHBoxLayout()
        hl.addWidget(QLabel('Min. Score:'))
        self._filter_score = QSpinBox()
        self._filter_score.setRange(0, 100)
        self._filter_score.setValue(30)
        self._filter_score.setFixedWidth(70)
        hl.addWidget(self._filter_score)

        load_btn = QPushButton('Laden')
        load_btn.clicked.connect(self._load_matches)
        hl.addWidget(load_btn)

        export_btn = QPushButton('CSV exportieren')
        export_btn.clicked.connect(self._export_csv)
        hl.addWidget(export_btn)

        hl.addStretch()
        self._matches_count = QLabel('')
        font = self._matches_count.font()
        font.setBold(True)
        self._matches_count.setFont(font)
        hl.addWidget(self._matches_count)
        vl.addLayout(hl)

        # Table
        self._matches_model = QStandardItemModel()
        self._matches_model.setHorizontalHeaderLabels(
            ['Score', 'Titel', 'Firma', 'Keywords', 'Datum', 'Top', 'Endkunde'])

        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._matches_model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        col_widths = [65, 0, 160, 240, 105, 45, 70]
        for i, w2 in enumerate(col_widths):
            if w2:
                self._table.setColumnWidth(i, w2)

        self._table.doubleClicked.connect(self._open_in_browser)
        self._table.selectionModel().selectionChanged.connect(self._show_detail)

        # Detail pane
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFixedHeight(130)
        self._detail.setPlaceholderText(
            'Zeile auswählen für Details  ·  Doppelklick öffnet Projektseite')

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        vl.addWidget(splitter)
        return w

    def _load_matches(self):
        db_path = os.path.join(BASE_DIR, 'freelancermap.db')
        if not os.path.exists(db_path):
            QMessageBox.warning(self, 'Datenbank fehlt',
                                'Bitte zuerst den Scraper ausführen.')
            return
        min_score = self._filter_score.value()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('''
            SELECT p.id, p.title, p.company, p.keywords, p.description,
                   p.created_date, p.link, p.is_top_project, p.is_endcustomer,
                   m.match_score, m.match_debug
            FROM matches m JOIN projects p ON m.project_id = p.id
            WHERE m.match_score >= ?
            ORDER BY m.match_score DESC
        ''', (min_score,))
        rows = cur.fetchall()
        conn.close()
        self._matches = [dict(r) for r in rows]
        self._populate_table()
        n = len(self._matches)
        self._matches_count.setText(f'{n} Match{"es" if n != 1 else ""}')
        self.statusBar().showMessage(
            f'{n} Matches geladen (Min-Score ≥ {min_score})')

    def _populate_table(self):
        model = self._matches_model
        model.setRowCount(0)
        for m in self._matches:
            score = QStandardItem()
            score.setData(round(m['match_score'], 1), Qt.ItemDataRole.DisplayRole)
            score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            title   = QStandardItem(m['title'] or '')
            company = QStandardItem(m['company'] or '')
            kw      = QStandardItem((m['keywords'] or '')[:60])
            date    = QStandardItem((m['created_date'] or '')[:10])
            top     = QStandardItem('★' if m.get('is_top_project') else '')
            top.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ec      = QStandardItem('✔' if m.get('is_endcustomer') else '')
            ec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            for item in (score, title, company, kw, date, top, ec):
                item.setEditable(False)
            model.appendRow([score, title, company, kw, date, top, ec])

        self._table.sortByColumn(0, Qt.SortOrder.DescendingOrder)

    def _open_in_browser(self, index):
        row = self._proxy.mapToSource(index).row()
        link = self._matches[row].get('link', '')
        if link and link != 'N/A':
            webbrowser.open(link)

    def _show_detail(self):
        idxs = self._table.selectionModel().selectedRows()
        if not idxs:
            return
        row = self._proxy.mapToSource(idxs[0]).row()
        m = self._matches[row]
        top_txt = ' ★ Top-Projekt' if m.get('is_top_project') else ''
        ec_txt  = ' ✔ Endkunde'   if m.get('is_endcustomer') else ''
        lines = [
            f"<b>{m['title']}</b>{top_txt}{ec_txt}",
            f"Firma: {m['company']}   |   Score: {m['match_score']:.1f}",
            f"Keywords: {m['keywords']}",
        ]
        desc = (m.get('description') or '')[:350]
        if desc:
            lines += ['', desc + ' …']
        debug = m.get('match_debug', '')
        if debug:
            lines += ['', '<b>Match-Debug:</b>', f'<pre>{debug}</pre>']
        self._detail.setHtml('<br>'.join(lines))

    def _export_csv(self):
        if not self._matches:
            QMessageBox.information(self, 'Keine Daten',
                                    'Bitte zuerst Matches laden.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'CSV speichern',
            os.path.join(BASE_DIR, f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
            'CSV (*.csv);;Alle Dateien (*)',
        )
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(['Titel', 'Firma', 'Score', 'Keywords',
                        'Datum', 'Top-Projekt', 'Endkunde', 'Link'])
            for m in self._matches:
                w.writerow([
                    m['title'], m['company'],
                    f"{m['match_score']:.2f}", m['keywords'],
                    m['created_date'],
                    'Ja' if m.get('is_top_project') else 'Nein',
                    'Ja' if m.get('is_endcustomer') else 'Nein',
                    m['link'],
                ])
        QMessageBox.information(self, 'Exportiert',
                                f'CSV gespeichert:\n{path}')
        self.statusBar().showMessage(f'Exportiert: {os.path.basename(path)}')

    # ------------------------------------------------------ Statistics tab

    def _build_statistics_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        btn = QPushButton('Statistiken laden')
        btn.setFixedWidth(160)
        btn.clicked.connect(self._load_statistics)
        vl.addWidget(btn)

        self._stats_view = QTextEdit()
        self._stats_view.setReadOnly(True)
        self._stats_view.setFont(QFont('Menlo' if sys.platform == 'darwin' else 'Courier New', 11))
        vl.addWidget(self._stats_view)
        return w

    def _load_statistics(self):
        db_path = os.path.join(BASE_DIR, 'freelancermap.db')
        if not os.path.exists(db_path):
            QMessageBox.warning(self, 'Datenbank fehlt',
                                'Bitte zuerst den Scraper ausführen.')
            return
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute('''
            SELECT AVG(match_score) as avg_score, COUNT(*) as total_matches,
                   MAX(m.match_date) as latest_match,
                   MIN(p.created_date) as oldest_project,
                   COUNT(DISTINCT p.company) as unique_companies
            FROM matches m JOIN projects p ON m.project_id = p.id
            WHERE m.match_date >= date('now', '-7 days')
        ''')
        stats = dict(cur.fetchone())

        cur.execute('SELECT COUNT(*) as c FROM projects')
        total_projects = cur.fetchone()['c']
        cur.execute('SELECT COUNT(*) as c FROM matches')
        total_matches_all = cur.fetchone()['c']

        cur.execute('''
            SELECT
                CASE
                    WHEN match_score < 30 THEN '0–30 '
                    WHEN match_score < 50 THEN '30–50'
                    WHEN match_score < 70 THEN '50–70'
                    ELSE '70–100'
                END as rng,
                COUNT(*) as cnt
            FROM matches GROUP BY rng ORDER BY MIN(match_score)
        ''')
        score_dist = cur.fetchall()

        cur.execute('''
            SELECT company, COUNT(*) as cnt, AVG(match_score) as avg_sc
            FROM matches m JOIN projects p ON m.project_id = p.id
            WHERE company != 'N/A'
            GROUP BY company ORDER BY cnt DESC LIMIT 10
        ''')
        top_cos = cur.fetchall()
        conn.close()

        lines = []
        sep = '─' * 54

        lines.append('<b style="font-size:14px">Übersicht</b>')
        lines.append(sep)
        lines.append(f'Projekte in Datenbank:     {total_projects}')
        lines.append(f'Matches gesamt:            {total_matches_all}')
        lines.append(f'Matches (letzte 7 Tage):   {stats["total_matches"]}')
        avg = stats.get('avg_score') or 0
        lines.append(f'Ø Match-Score (7 Tage):    {avg:.2f}')
        lines.append(f'Neuestes Match:            {stats["latest_match"] or "–"}')
        lines.append(f'Ältestes Projekt:          {stats["oldest_project"] or "–"}')
        lines.append(f'Eindeutige Unternehmen:    {stats["unique_companies"]}')
        lines.append('')

        lines.append('<b style="font-size:13px">Score-Verteilung (alle Matches)</b>')
        lines.append(sep)
        for row in score_dist:
            bar = '█' * min(int(row['cnt'] / max(total_matches_all, 1) * 40), 40)
            lines.append(f'{row["rng"]}  {row["cnt"]:5d}  {bar}')
        lines.append('')

        lines.append('<b style="font-size:13px">Top 10 Unternehmen</b>')
        lines.append(sep)
        for row in top_cos:
            lines.append(
                f'{row["company"][:36]:36s}  {row["cnt"]:3d}  Ø {row["avg_sc"]:.1f}')

        self._stats_view.setHtml('<pre>' + '\n'.join(lines) + '</pre>')
        self.statusBar().showMessage('Statistiken geladen')


# ------------------------------------------------------------------- main

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Freelancermap Crawler')

    # macOS: use native style
    if sys.platform == 'darwin':
        app.setStyle('macos')

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

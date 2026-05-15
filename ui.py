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
import threading
import queue
import sqlite3
import webbrowser
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSortFilterProxyModel
from PyQt6.QtGui import QFont, QColor, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QTextEdit,
    QTableView, QHeaderView, QProgressBar, QFileDialog,
    QMessageBox, QGroupBox, QCheckBox, QStatusBar, QSplitter,
    QAbstractItemView,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, '.env')
UI_CONFIG_FILE = os.path.join(BASE_DIR, 'ui_config.json')

DEFAULT_CONFIG = {
    'username': '',
    'password': '',
    'max_pages': 10,
    'min_score': 35,
    'skills': 'Python, JavaScript, React, Vue, MySQL, HTML, CSS, PHP, GCP, AWS, Cloud, AI, Frontend, Vue.js, JS',
    'preferred_keywords': 'Webentwicklung, Backend, Frontend, Fullstack, API, Wordpress, GCP, AWS, Cloud, AI, OpenAI',
    'excluded_keywords': 'SAP, Drupal',
}


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

            self.log.emit(f'Starte Scraping  |  Seiten: {max_pages}  |  Min-Score: {min_score}', 'info')
            self.log.emit(f'Skills: {", ".join(profile["skills"][:8])} …', 'info')

            db = projectMatcher.FreelancermapDatabase()
            scraper = projectMatcher.FreelancermapScraper(
                db=db,
                username=self.config['username'],
                password=self.config['password'],
                max_pages=max_pages,
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
        fl2.addRow('Max. Seiten:', self._max_pages)
        fl2.addRow('Min. Score (0–100):', self._min_score)
        root.addWidget(sc)

        # Profile
        pr = QGroupBox('Profil')
        fl3 = QFormLayout(pr)
        fl3.setSpacing(8)
        self._skills    = QLineEdit(self.config['skills'])
        self._preferred = QLineEdit(self.config['preferred_keywords'])
        self._excluded  = QLineEdit(self.config['excluded_keywords'])
        fl3.addRow('Skills (kommagetrennt):', self._skills)
        fl3.addRow('Bevorzugte Keywords:', self._preferred)
        fl3.addRow('Ausgeschlossene Keywords:', self._excluded)
        root.addWidget(pr)

        root.addStretch()
        btn = QPushButton('Einstellungen speichern')
        btn.clicked.connect(self._save_config)
        hl = QHBoxLayout()
        hl.addStretch()
        hl.addWidget(btn)
        root.addLayout(hl)
        return w

    def _save_config(self):
        self.config.update({
            'username':           self._username.text(),
            'password':           self._password.text(),
            'max_pages':          self._max_pages.value(),
            'min_score':          self._min_score.value(),
            'skills':             self._skills.text(),
            'preferred_keywords': self._preferred.text(),
            'excluded_keywords':  self._excluded.text(),
        })
        save_config(self.config)
        self.statusBar().showMessage('Einstellungen gespeichert.')

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

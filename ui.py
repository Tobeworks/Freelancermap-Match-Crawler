#!/usr/bin/env python3
"""
Freelancermap Match Crawler - Desktop UI
Cross-platform: macOS, Windows, Linux (tkinter)
"""

import os
import sys
import json
import csv
import threading
import queue
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, '.env')
UI_CONFIG_FILE = os.path.join(BASE_DIR, 'ui_config.json')

DEFAULT_CONFIG = {
    'username': '',
    'password': '',
    'max_pages': '10',
    'min_score': '35',
    'skills': 'Python, JavaScript, React, Vue, MySQL, HTML, CSS, PHP, GCP, AWS, Cloud, AI, Frontend, Vue.js, JS',
    'preferred_keywords': 'Webentwicklung, Backend, Frontend, Fullstack, API, Wordpress, GCP, AWS, Cloud, AI, OpenAI',
    'excluded_keywords': 'SAP, Drupal',
}


def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
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
        with open(UI_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config.update(json.load(f))
    return config


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"FREELANCERMAP_USERNAME={config['username']}\n")
        f.write(f"FREELANCERMAP_PASSWORD={config['password']}\n")
    extra = {k: v for k, v in config.items() if k not in ('username', 'password')}
    with open(UI_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(extra, f, indent=2, ensure_ascii=False)


class RedirectToQueue:
    """Captures stdout/stderr and forwards lines to a queue."""
    def __init__(self, q, tag='info'):
        self.q = q
        self.tag = tag
        self.buf = ''

    def write(self, text):
        self.buf += text
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            if line.strip():
                self.q.put((line, self.tag))

    def flush(self):
        if self.buf.strip():
            self.q.put((self.buf, self.tag))
            self.buf = ''


class FreelancermapUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Freelancermap Match Crawler")
        self.root.geometry("1050x720")
        self.root.minsize(800, 580)

        self.config = load_config()
        self.log_queue = queue.Queue()
        self.scraper_thread = None
        self.scraping = False
        self._matches_data = []
        self._sort_column = 'score'
        self._sort_reverse = True

        self._setup_styles()
        self._build_ui()
        self._process_log_queue()

    # ------------------------------------------------------------------ styles

    def _setup_styles(self):
        style = ttk.Style()
        for theme in ('clam', 'alt', 'default'):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        style.configure('TNotebook.Tab', padding=[14, 6], font=('TkDefaultFont', 10))
        style.configure('Bold.TLabel', font=('TkDefaultFont', 10, 'bold'))
        style.configure('Status.TLabel', font=('TkDefaultFont', 9))
        style.configure('Run.TButton', font=('TkDefaultFont', 10, 'bold'), padding=6)

    # ------------------------------------------------------------------ layout

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=6)
        main.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Bereit")
        ttk.Label(self.root, textvariable=self.status_var,
                  style='Status.TLabel', relief=tk.SUNKEN,
                  anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=1)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_config_tab()
        self._build_crawler_tab()
        self._build_matches_tab()
        self._build_statistics_tab()

    # ---------------------------------------------------------- Konfiguration

    def _build_config_tab(self):
        f = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(f, text='  Konfiguration  ')

        # --- Anmeldedaten ---
        cred = ttk.LabelFrame(f, text='Anmeldedaten (freelancermap.de)', padding=10)
        cred.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(cred, text='E-Mail:').grid(row=0, column=0, sticky=tk.W, pady=4)
        self.username_var = tk.StringVar(value=self.config['username'])
        ttk.Entry(cred, textvariable=self.username_var, width=45).grid(
            row=0, column=1, sticky=tk.EW, padx=(10, 0))

        ttk.Label(cred, text='Passwort:').grid(row=1, column=0, sticky=tk.W, pady=4)
        self.password_var = tk.StringVar(value=self.config['password'])
        self._pw_entry = ttk.Entry(cred, textvariable=self.password_var,
                                   show='*', width=45)
        self._pw_entry.grid(row=1, column=1, sticky=tk.EW, padx=(10, 0))

        self._show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(cred, text='anzeigen', variable=self._show_pw,
                        command=self._toggle_password).grid(row=1, column=2, padx=6)
        cred.columnconfigure(1, weight=1)

        # --- Scraper-Einstellungen ---
        sc = ttk.LabelFrame(f, text='Scraper-Einstellungen', padding=10)
        sc.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(sc, text='Max. Seiten:').grid(row=0, column=0, sticky=tk.W, pady=4)
        self.max_pages_var = tk.StringVar(value=self.config['max_pages'])
        ttk.Spinbox(sc, textvariable=self.max_pages_var,
                    from_=1, to=200, width=8).grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        ttk.Label(sc, text='Min. Score (0–100):').grid(row=1, column=0, sticky=tk.W, pady=4)
        self.min_score_var = tk.StringVar(value=self.config['min_score'])
        ttk.Spinbox(sc, textvariable=self.min_score_var,
                    from_=0, to=100, width=8).grid(row=1, column=1, sticky=tk.W, padx=(10, 0))

        # --- Profil ---
        pr = ttk.LabelFrame(f, text='Profil', padding=10)
        pr.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        labels = [
            ('Skills (kommagetrennt):', 'skills_var', self.config['skills']),
            ('Bevorzugte Keywords:', 'preferred_var', self.config['preferred_keywords']),
            ('Ausgeschlossene Keywords:', 'excluded_var', self.config['excluded_keywords']),
        ]
        for row, (text, attr, val) in enumerate(labels):
            ttk.Label(pr, text=text).grid(row=row, column=0, sticky=tk.NW, pady=5)
            var = tk.StringVar(value=val)
            setattr(self, attr, var)
            ttk.Entry(pr, textvariable=var, width=72).grid(
                row=row, column=1, sticky=tk.EW, padx=(10, 0), pady=5)
        pr.columnconfigure(1, weight=1)

        ttk.Button(f, text='Einstellungen speichern',
                   command=self._save_config).pack(anchor=tk.E)

    def _toggle_password(self):
        self._pw_entry.configure(show='' if self._show_pw.get() else '*')

    # -------------------------------------------------------------- Crawler

    def _build_crawler_tab(self):
        f = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(f, text='  Crawler  ')

        ctrl = ttk.Frame(f)
        ctrl.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = ttk.Button(ctrl, text='▶  Scraping starten',
                                    style='Run.TButton', command=self._start_scraping)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(ctrl, text='■  Stoppen',
                                   command=self._stop_scraping, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(ctrl, text='Log leeren', command=self._clear_log).pack(side=tk.LEFT)

        self.progress_label = tk.StringVar(value='')
        ttk.Label(ctrl, textvariable=self.progress_label).pack(side=tk.RIGHT)

        self.progress_bar = ttk.Progressbar(f, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 6))

        log_frame = ttk.LabelFrame(f, text='Ausgabe', padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame, wrap=tk.WORD,
            font=('Courier New' if sys.platform == 'win32' else 'Courier', 9),
            bg='#1e1e1e', fg='#d4d4d4', insertbackground='white',
            state=tk.DISABLED, relief=tk.FLAT,
        )
        vsb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log_text.tag_configure('info',      foreground='#d4d4d4')
        self.log_text.tag_configure('success',   foreground='#4ec9b0')
        self.log_text.tag_configure('error',     foreground='#f44747')
        self.log_text.tag_configure('warning',   foreground='#dcdcaa')
        self.log_text.tag_configure('timestamp', foreground='#858585')

    # -------------------------------------------------------------- Matches

    def _build_matches_tab(self):
        f = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(f, text='  Matches  ')

        toolbar = ttk.Frame(f)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(toolbar, text='Min. Score:').pack(side=tk.LEFT)
        self.filter_score_var = tk.StringVar(value='30')
        ttk.Spinbox(toolbar, textvariable=self.filter_score_var,
                    from_=0, to=100, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text='Laden', command=self._load_matches).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text='CSV exportieren', command=self._export_csv).pack(side=tk.LEFT, padx=4)

        self.matches_count_var = tk.StringVar(value='')
        ttk.Label(toolbar, textvariable=self.matches_count_var,
                  style='Bold.TLabel').pack(side=tk.RIGHT)

        # --- Treeview ---
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ('score', 'title', 'company', 'keywords', 'date', 'top', 'ec')
        self.matches_tree = ttk.Treeview(tree_frame, columns=cols,
                                          show='headings', selectmode='browse')

        headers = {
            'score':    ('Score',      70,  tk.CENTER),
            'title':    ('Titel',      310, tk.W),
            'company':  ('Firma',      150, tk.W),
            'keywords': ('Keywords',   240, tk.W),
            'date':     ('Datum',      110, tk.W),
            'top':      ('Top',         45, tk.CENTER),
            'ec':       ('Endkunde',    70, tk.CENTER),
        }
        for col, (text, width, anchor) in headers.items():
            self.matches_tree.heading(
                col, text=text,
                command=lambda c=col: self._sort_matches(c))
            self.matches_tree.column(col, width=width, anchor=anchor, stretch=(col == 'title'))

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                             command=self.matches_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL,
                             command=self.matches_tree.xview)
        self.matches_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.matches_tree.pack(fill=tk.BOTH, expand=True)

        self.matches_tree.bind('<Double-1>', self._open_match_browser)
        self.matches_tree.bind('<Return>', self._open_match_browser)
        self.matches_tree.bind('<<TreeviewSelect>>', self._show_match_detail)

        # --- Detail pane ---
        detail_frame = ttk.LabelFrame(f, text='Details  (Doppelklick öffnet Projektseite)', padding=5)
        detail_frame.pack(fill=tk.X, pady=(8, 0))

        self.detail_text = tk.Text(detail_frame, height=6, wrap=tk.WORD,
                                    font=('TkDefaultFont', 9), state=tk.DISABLED)
        dsb = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=dsb.set)
        dsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.detail_text.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------ Statistiken

    def _build_statistics_tab(self):
        f = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(f, text='  Statistiken  ')

        ttk.Button(f, text='Statistiken laden',
                   command=self._load_statistics).pack(anchor=tk.W, pady=(0, 10))

        txt_frame = ttk.Frame(f)
        txt_frame.pack(fill=tk.BOTH, expand=True)

        self.stats_text = tk.Text(
            txt_frame, wrap=tk.WORD,
            font=('TkDefaultFont', 10), state=tk.DISABLED,
            padx=12, pady=8, relief=tk.FLAT,
        )
        ssb = ttk.Scrollbar(txt_frame, orient=tk.VERTICAL, command=self.stats_text.yview)
        self.stats_text.configure(yscrollcommand=ssb.set)
        ssb.pack(side=tk.RIGHT, fill=tk.Y)
        self.stats_text.pack(fill=tk.BOTH, expand=True)

        self.stats_text.tag_configure('h1', font=('TkDefaultFont', 13, 'bold'))
        self.stats_text.tag_configure('h2', font=('TkDefaultFont', 11, 'bold'))
        self.stats_text.tag_configure('mono', font=('Courier', 10))
        self.stats_text.tag_configure('muted', foreground='#666666')

    # ============================== actions ==================================

    def _save_config(self):
        self.config.update({
            'username':          self.username_var.get(),
            'password':          self.password_var.get(),
            'max_pages':         self.max_pages_var.get(),
            'min_score':         self.min_score_var.get(),
            'skills':            self.skills_var.get(),
            'preferred_keywords': self.preferred_var.get(),
            'excluded_keywords': self.excluded_var.get(),
        })
        save_config(self.config)
        self.status_var.set('Einstellungen gespeichert.')

    # -------------------------------------------------------------- Crawler

    def _start_scraping(self):
        if not self.username_var.get() or not self.password_var.get():
            messagebox.showerror('Fehler', 'Bitte E-Mail und Passwort in der Konfiguration eintragen.')
            self.notebook.select(0)
            return

        self._save_config()
        self.scraping = True
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.progress_bar.start(12)
        self.status_var.set('Scraping läuft …')
        self.notebook.select(1)

        self.scraper_thread = threading.Thread(target=self._run_scraper, daemon=True)
        self.scraper_thread.start()

    def _stop_scraping(self):
        self.scraping = False
        self.log('Stopp-Signal gesendet …', 'warning')

    def _run_scraper(self):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = RedirectToQueue(self.log_queue, 'info')
        sys.stderr = RedirectToQueue(self.log_queue, 'error')
        try:
            import importlib
            import projectMatcher
            importlib.reload(projectMatcher)

            profile = {
                'skills':             [s.strip() for s in self.config['skills'].split(',') if s.strip()],
                'preferred_keywords': [s.strip() for s in self.config['preferred_keywords'].split(',') if s.strip()],
                'excluded_keywords':  [s.strip() for s in self.config['excluded_keywords'].split(',') if s.strip()],
            }
            max_pages = max(1, int(self.config['max_pages']))
            min_score = int(self.config['min_score'])

            self.log(f'Starte Scraping  |  Seiten: {max_pages}  |  Min-Score: {min_score}', 'info')
            self.log(f'Skills: {", ".join(profile["skills"][:6])} …', 'info')

            db = projectMatcher.FreelancermapDatabase()
            scraper = projectMatcher.FreelancermapScraper(
                db=db,
                username=self.config['username'],
                password=self.config['password'],
                max_pages=max_pages,
            )

            if not scraper.login():
                self.log('Login fehlgeschlagen – Zugangsdaten prüfen.', 'error')
                return

            import time, random as rnd
            scraped = 0
            for page in range(1, max_pages + 1):
                if not self.scraping:
                    self.log('Scraping gestoppt.', 'warning')
                    break
                projects = scraper.get_page(page)
                if not projects:
                    self.log(f'Seite {page}: keine Projekte mehr – beende.', 'warning')
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
                self.root.after(0, lambda n=scraped: self.progress_label.set(f'{n} Projekte'))
                if page < max_pages and self.scraping:
                    time.sleep(rnd.uniform(2, 4))

            if self.scraping:
                self.log(f'{scraped} Projekte gespeichert. Starte Matching …', 'success')
                matcher = projectMatcher.ProjectMatcher(db)
                matcher.find_matches(profile, min_score=min_score)
                try:
                    stats = matcher.get_statistics()
                    total = stats.get('total_matches', 0)
                    avg   = stats.get('avg_score') or 0
                    self.log(f'Fertig!  Matches: {total}  |  Ø Score: {avg:.1f}', 'success')
                    self.root.after(0, lambda t=total: self.status_var.set(
                        f'Scraping abgeschlossen – {t} Matches gefunden.'))
                except Exception:
                    self.log('Matching abgeschlossen.', 'success')
                    self.root.after(0, lambda: self.status_var.set('Scraping abgeschlossen.'))

        except Exception as exc:
            import traceback
            self.log(f'Fehler: {exc}', 'error')
            self.log(traceback.format_exc(), 'error')
            self.root.after(0, lambda e=str(exc): self.status_var.set(f'Fehler: {e}'))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.scraping = False
            self.root.after(0, self._scraping_done)

    def _scraping_done(self):
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.progress_bar.stop()

    def log(self, message, tag='info'):
        self.log_queue.put((message, tag))

    def _process_log_queue(self):
        while not self.log_queue.empty():
            message, tag = self.log_queue.get_nowait()
            self.log_text.configure(state=tk.NORMAL)
            ts = datetime.now().strftime('%H:%M:%S')
            self.log_text.insert(tk.END, f'[{ts}] ', 'timestamp')
            self.log_text.insert(tk.END, f'{message}\n', tag)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.root.after(100, self._process_log_queue)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # -------------------------------------------------------------- Matches

    def _load_matches(self):
        db_path = os.path.join(BASE_DIR, 'freelancermap.db')
        if not os.path.exists(db_path):
            messagebox.showwarning('Datenbank fehlt',
                                   'Bitte zuerst den Scraper ausführen.')
            return
        try:
            min_score = float(self.filter_score_var.get())
        except ValueError:
            min_score = 30.0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('''
            SELECT p.id, p.title, p.company, p.keywords, p.description,
                   p.created_date, p.link, p.is_top_project, p.is_endcustomer,
                   m.match_score, m.match_debug
            FROM matches m
            JOIN projects p ON m.project_id = p.id
            WHERE m.match_score >= ?
            ORDER BY m.match_score DESC
        ''', (min_score,))
        rows = cur.fetchall()
        conn.close()

        self._matches_data = [dict(r) for r in rows]
        self._sort_column = 'score'
        self._sort_reverse = True
        self._populate_matches_tree()
        n = len(self._matches_data)
        self.matches_count_var.set(f'{n} Match{"es" if n != 1 else ""}')
        self.status_var.set(f'{n} Matches geladen (Min-Score ≥ {min_score:.0f})')

    def _populate_matches_tree(self):
        self.matches_tree.delete(*self.matches_tree.get_children())
        for i, m in enumerate(self._matches_data):
            score  = f"{m['match_score']:.1f}"
            date   = (m['created_date'] or '')[:10]
            kw     = (m['keywords'] or '')[:55]
            top    = '★' if m.get('is_top_project') else ''
            ec     = '✔' if m.get('is_endcustomer') else ''
            tag    = 'odd' if i % 2 == 0 else 'even'
            self.matches_tree.insert('', tk.END, iid=str(i),
                values=(score, m['title'], m['company'], kw, date, top, ec),
                tags=(tag,))
        self.matches_tree.tag_configure('odd',  background='#f5f5f5')
        self.matches_tree.tag_configure('even', background='#ffffff')

    def _sort_matches(self, col):
        if self._sort_column == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = col
            self._sort_reverse = (col == 'score')

        key_map = {
            'score':   'match_score',
            'title':   'title',
            'company': 'company',
            'date':    'created_date',
            'top':     'is_top_project',
            'ec':      'is_endcustomer',
        }
        key = key_map.get(col, col)
        self._matches_data.sort(
            key=lambda x: (x.get(key) or 0 if col == 'score' else x.get(key) or ''),
            reverse=self._sort_reverse,
        )
        self._populate_matches_tree()

    def _open_match_browser(self, _event=None):
        sel = self.matches_tree.selection()
        if not sel:
            return
        m = self._matches_data[int(sel[0])]
        link = m.get('link', '')
        if link and link != 'N/A':
            webbrowser.open(link)

    def _show_match_detail(self, _event=None):
        sel = self.matches_tree.selection()
        if not sel:
            return
        m = self._matches_data[int(sel[0])]

        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete('1.0', tk.END)
        self.detail_text.insert(tk.END, f"Titel:    {m['title']}\n")
        self.detail_text.insert(tk.END, f"Firma:    {m['company']}   |   Score: {m['match_score']:.1f}\n")
        self.detail_text.insert(tk.END, f"Keywords: {m['keywords']}\n")
        desc = (m.get('description') or '')[:350]
        if desc:
            self.detail_text.insert(tk.END, f"\n{desc}…\n")
        debug = m.get('match_debug', '')
        if debug:
            self.detail_text.insert(tk.END, f"\nMatch-Debug:\n{debug}\n")
        self.detail_text.configure(state=tk.DISABLED)

    def _export_csv(self):
        if not self._matches_data:
            messagebox.showinfo('Keine Daten', 'Bitte zuerst Matches laden.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV', '*.csv'), ('Alle Dateien', '*.*')],
            initialfile=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(['Titel', 'Firma', 'Score', 'Keywords',
                        'Datum', 'Top-Projekt', 'Endkunde', 'Link'])
            for m in self._matches_data:
                w.writerow([
                    m['title'], m['company'],
                    f"{m['match_score']:.2f}", m['keywords'],
                    m['created_date'],
                    'Ja' if m.get('is_top_project') else 'Nein',
                    'Ja' if m.get('is_endcustomer') else 'Nein',
                    m['link'],
                ])
        messagebox.showinfo('Exportiert', f'CSV gespeichert:\n{path}')
        self.status_var.set(f'Exportiert: {os.path.basename(path)}')

    # ------------------------------------------------------------ Statistiken

    def _load_statistics(self):
        db_path = os.path.join(BASE_DIR, 'freelancermap.db')
        if not os.path.exists(db_path):
            messagebox.showwarning('Datenbank fehlt',
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

        cur.execute("SELECT COUNT(*) as c FROM projects")
        total_projects = cur.fetchone()['c']

        cur.execute("SELECT COUNT(*) as c FROM matches")
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
            FROM matches
            GROUP BY rng
            ORDER BY MIN(match_score)
        ''')
        score_dist = cur.fetchall()

        cur.execute('''
            SELECT company, COUNT(*) as cnt, AVG(match_score) as avg_sc
            FROM matches m JOIN projects p ON m.project_id = p.id
            WHERE company != 'N/A'
            GROUP BY company
            ORDER BY cnt DESC LIMIT 10
        ''')
        top_companies = cur.fetchall()
        conn.close()

        t = self.stats_text
        t.configure(state=tk.NORMAL)
        t.delete('1.0', tk.END)

        def line(text, tag=''):
            t.insert(tk.END, text + '\n', tag)

        line('Übersicht', 'h1')
        line('─' * 52, 'muted')
        line(f'  Projekte in Datenbank:     {total_projects}')
        line(f'  Matches gesamt:            {total_matches_all}')
        line(f'  Matches (letzte 7 Tage):   {stats["total_matches"]}')
        avg = stats.get('avg_score') or 0
        line(f'  Ø Match-Score (7 Tage):    {avg:.2f}')
        line(f'  Neuestes Match:            {stats["latest_match"] or "–"}')
        line(f'  Ältestes Projekt:          {stats["oldest_project"] or "–"}')
        line(f'  Eindeutige Unternehmen:    {stats["unique_companies"]}')
        line('')

        line('Score-Verteilung (alle Matches)', 'h2')
        line('─' * 52, 'muted')
        for row in score_dist:
            bar = '█' * min(int(row['cnt'] / max(total_matches_all, 1) * 40), 40)
            line(f'  {row["rng"]}  {row["cnt"]:5d}  {bar}', 'mono')
        line('')

        line('Top 10 Unternehmen', 'h2')
        line('─' * 52, 'muted')
        for row in top_companies:
            line(f'  {row["company"][:36]:36s}  {row["cnt"]:3d}  Ø {row["avg_sc"]:.1f}', 'mono')

        t.configure(state=tk.DISABLED)
        self.status_var.set('Statistiken geladen')


# ============================================================= entry point

def main():
    root = tk.Tk()

    # macOS: bring window to front on re-open
    if sys.platform == 'darwin':
        try:
            root.createcommand('tk::mac::ReopenApplication', root.lift)
        except Exception:
            pass

    # Windows: set DPI awareness for sharper rendering
    if sys.platform == 'win32':
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    app = FreelancermapUI(root)  # noqa: F841
    root.mainloop()


if __name__ == '__main__':
    main()

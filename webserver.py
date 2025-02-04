import os
import sqlite3
from flask import Flask, render_template, request, g
from werkzeug.middleware.proxy_fix import ProxyFix
import sys

# Ensure the script can find its templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# Create templates directory if it doesn't exist
os.makedirs(TEMPLATE_DIR, exist_ok=True)

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.wsgi_app = ProxyFix(app.wsgi_app)

# Database path (can be adjusted)
DATABASE = os.path.join(BASE_DIR, 'freelancermap.db')

def get_db():
    """Establish a database connection."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    """Main page with project matches."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    # Get total matches
    cur = get_db().cursor()
    cur.execute("""
        SELECT COUNT(*) as total 
        FROM matches 
        WHERE match_score >= 30
    """)
    total_matches = cur.fetchone()['total']
    total_pages = (total_matches + per_page - 1) // per_page

    # Fetch matches with pagination
    cur.execute("""
        SELECT 
            p.title, 
            p.company, 
            p.keywords, 
            substr(p.description, 1, 300) as description, 
            p.created_date, 
            p.link, 
            p.is_top_project,
            p.is_endcustomer, 
            m.match_score, 
            m.match_debug
        FROM matches m
        JOIN projects p ON m.project_id = p.id
        WHERE m.match_score >= 30
        ORDER BY m.match_score DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    
    matches = cur.fetchall()

    return render_template('index.html', 
                           matches=matches, 
                           page=page, 
                           total_pages=total_pages,
                           total_matches=total_matches)

@app.route('/project/<int:project_id>')
def project_detail(project_id):
    """Detailed view of a specific project."""
    cur = get_db().cursor()
    cur.execute("""
        SELECT 
            p.*, 
            m.match_score, 
            m.match_debug
        FROM projects p
        JOIN matches m ON p.id = m.project_id
        WHERE p.id = ?
    """, (project_id,))
    
    project = cur.fetchone()
    
    if not project:
        return "Project not found", 404
    
    return render_template('project_detail.html', project=project)

@app.route('/statistics')
def statistics():
    """Display project matching statistics."""
    cur = get_db().cursor()
    
    # Overall statistics
    cur.execute("""
        SELECT 
            AVG(match_score) as avg_score,
            COUNT(*) as total_matches,
            MAX(match_date) as latest_match,
            MIN(created_date) as oldest_project,
            COUNT(DISTINCT company) as unique_companies
        FROM matches m
        JOIN projects p ON m.project_id = p.id
        WHERE m.match_date >= date('now', '-7 days')
    """)
    stats = cur.fetchone()
    
    # Score distribution
    cur.execute("""
        SELECT 
            CASE 
                WHEN match_score < 30 THEN '0-30'
                WHEN match_score BETWEEN 30 AND 50 THEN '30-50'
                WHEN match_score BETWEEN 50 AND 70 THEN '50-70'
                ELSE '70-100'
            END as score_range,
            COUNT(*) as count
        FROM matches
        GROUP BY score_range
        ORDER BY 
            CASE score_range
                WHEN '0-30' THEN 1
                WHEN '30-50' THEN 2
                WHEN '50-70' THEN 3
                ELSE 4
            END
    """)
    score_distribution = cur.fetchall()
    
    # Top companies
    cur.execute("""
        SELECT 
            company, 
            COUNT(*) as project_count, 
            AVG(match_score) as avg_match_score
        FROM matches m
        JOIN projects p ON m.project_id = p.id
        WHERE company != 'N/A'
        GROUP BY company
        ORDER BY project_count DESC
        LIMIT 10
    """)
    top_companies = cur.fetchall()
    
    return render_template('statistics.html', 
                           stats=stats, 
                           score_distribution=score_distribution,
                           top_companies=top_companies)

def create_templates():
    """Create template files in the templates directory."""
    templates = {
        'base.html': '''
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>{% block title %}Freelancermap Matches{% endblock %}</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    border-bottom: 1px solid #eee;
                    padding-bottom: 10px;
                }
                .nav a {
                    margin-left: 10px;
                    text-decoration: none;
                    color: #333;
                }
                .project-card {
                    border: 1px solid #ddd;
                    margin-bottom: 15px;
                    padding: 15px;
                    border-radius: 5px;
                }
                .pagination {
                    display: flex;
                    justify-content: center;
                    margin-top: 20px;
                }
                .badge {
                    display: inline-block;
                    padding: 3px 6px;
                    margin-right: 5px;
                    border-radius: 3px;
                    font-size: 0.8em;
                }
                .top-project { background-color: #e7f3fe; color: #0c5460; }
                .endcustomer { background-color: #d4edda; color: #155724; }
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{% block header %}Freelancermap Matches{% endblock %}</h1>
                <div class="nav">
                    <a href="/">Matches</a>
                    <a href="/statistics">Statistiken</a>
                </div>
            </div>
            {% block content %}{% endblock %}
        </body>
        </html>
        ''',
        
        'index.html': '''
        {% extends "base.html" %}

        {% block title %}Freelancermap Projekt-Matches{% endblock %}

        {% block content %}
        <h2>Gefundene Matches ({{ total_matches }} Projekte)</h2>
        {% for match in matches %}
        <div class="project-card">
            <h3>
                <a href="{{ match['link'] }}" target="_blank">{{ match['title'] }}</a>
                {% if match['is_top_project'] %}
                    <span class="badge top-project">Top Projekt</span>
                {% endif %}
                {% if match['is_endcustomer'] %}
                    <span class="badge endcustomer">Endkunde</span>
                {% endif %}
            </h3>
            <p><strong>Firma:</strong> {{ match['company'] }}</p>
            <p><strong>Keywords:</strong> {{ match['keywords'] }}</p>
            <p>{{ match['description'] }}...</p>
            <p>
                <strong>Eingetragen:</strong> {{ match['created_date'] }} | 
                <strong>Match Score:</strong> {{ match['match_score']|round(2) }}
            </p>
        </div>
        {% endfor %}

        <div class="pagination">
            {% if page > 1 %}
                <a href="/?page={{ page - 1 }}">Vorherige</a>
            {% endif %}
            Seite {{ page }} von {{ total_pages }}
            {% if page < total_pages %}
                <a href="/?page={{ page + 1 }}">Nächste</a>
            {% endif %}
        </div>
        {% endblock %}
        ''',
        
        'project_detail.html': '''
        {% extends "base.html" %}

        {% block title %}Projektdetails{% endblock %}

        {% block content %}
        <div class="project-card">
            <h2>
                <a href="{{ project['link'] }}" target="_blank">{{ project['title'] }}</a>
                {% if project['is_top_project'] %}
                    <span class="badge top-project">Top Projekt</span>
                {% endif %}
                {% if project['is_endcustomer'] %}
                    <span class="badge endcustomer">Endkunde</span>
                {% endif %}
            </h2>
            <p><strong>Firma:</strong> {{ project['company'] }}</p>
            <p><strong>Keywords:</strong> {{ project['keywords'] }}</p>
            <p><strong>Beschreibung:</strong> {{ project['description'] }}</p>
            <p><strong>Eingetragen:</strong> {{ project['created_date'] }}</p>
            
            <h3>Match Details</h3>
            <p><strong>Match Score:</strong> {{ project['match_score']|round(2) }}</p>
            <pre>{{ project['match_debug'] }}</pre>
        </div>
        {% endblock %}
        ''',
        
        'statistics.html': '''
        {% extends "base.html" %}

        {% block title %}Projektstatistiken{% endblock %}

        {% block content %}
        <h2>Projektstatistiken</h2>
        
        <div class="project-card">
            <h3>Übersicht</h3>
            <p><strong>Gesamtzahl Matches:</strong> {{ stats['total_matches'] }}</p>
            <p><strong>Durchschnittlicher Match Score:</strong> {{ (stats['avg_score'] or 0)|round(2) }}</p>
            <p><strong>Neuestes Match:</strong> {{ stats['latest_match'] }}</p>
            <p><strong>Ältestes Projekt:</strong> {{ stats['oldest_project'] }}</p>
            <p><strong>Eindeutige Unternehmen:</strong> {{ stats['unique_companies'] }}</p>
        </div>

        <div class="project-card">
            <h3>Score-Verteilung</h3>
            <table>
                <tr>
                    <th>Score-Bereich</th>
                    <th>Anzahl Projekte</th>
                </tr>
                {% for dist in score_distribution %}
                <tr>
                    <td>{{ dist['score_range'] }}</td>
                    <td>{{ dist['count'] }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div class="project-card">
            <h3>Top 10 Unternehmen</h3>
            <table>
                <tr>
                    <th>Unternehmen</th>
                    <th>Projektanzahl</th>
                    <th>Durchschnittlicher Match Score</th>
                </tr>
                {% for company in top_companies %}
                <tr>
                    <td>{{ company['company'] }}</td>
                    <td>{{ company['project_count'] }}</td>
                    <td>{{ company['avg_match_score']|round(2) }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% endblock %}
        '''
    }

    # Write templates
    for filename, content in templates.items():
        filepath = os.path.join(TEMPLATE_DIR, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Created template: {filename}")
        except Exception as e:
            print(f"Error creating template {filename}: {e}")


if __name__ == '__main__':

    create_templates()

    # Print database location for debugging
    print(f"Database location: {DATABASE}")
    
    # Try to provide more information if database is not found
    if not os.path.exists(DATABASE):
        print("ERROR: Database file not found!")
        print(f"Please ensure {DATABASE} exists.")
        sys.exit(1)
    
    # Run the app
    app.run(debug=True)

# Expose the app for WSGI servers
if __name__ != '__main__':
    create_templates()
# Freelancermap Project Scraper & Matcher

This Python script scrapes projects from freelancermap.de and matches them against your skill profile. It stores the data in a SQLite database and exports matches as CSV.

## Features

- Scrapes project listings from freelancermap.de 
- Stores complete project data in SQLite database
- Matches projects against customizable skill profile
- Scoring based on:
  - Exact keyword matches (30 points)
  - Partial keyword matches (20 points) 
  - Description matches (30 points)
  - Project age (20 points)
- Exports matches as CSV with detailed debug information
- 100% remote projects only (German speaking region)

## Installation

1. Clone this repository
2. Install requirements:
```bash
pip install -r requirements.txt
```

3. Create `.env` file with your freelancermap.de credentials:
```env
FREELANCERMAP_USERNAME=your@email.com
FREELANCERMAP_PASSWORD=your_password
```

## Usage

1. Customize your profile in `main.py`:
```python
profile = {
    'skills': ['Python', 'JavaScript', 'React', ...],
    'preferred_keywords': ['Backend', 'Frontend', ...],
    'excluded_keywords': ['SAP', 'Drupal']
}
```

2. Run the script:
```bash
python projectMatcher.py
```

## Database Inspection

For a quick web interface to inspect the SQLite database, use `sqlite-web`:

```bash
# Install sqlite-web
pip install sqlite-web

# Start the web interface
sqlite_web freelancermap.db

# Or with specific host/port
sqlite_web -H 0.0.0.0 -p 8080 freelancermap.db
```



3. Check the generated CSV file with matches

## Match Scoring

Projects are scored on a 100 point scale:
- Keywords (50 points):
  - Exact matches: 30 points max
  - Partial matches: 20 points max
- Description matches (30 points):
  - Skills found: 20 points max
  - Preferred keywords: 10 points max
- Project age (20 points):
  - Exponential decay over 15 days

## Database Schema

### Projects Table
- id (PRIMARY KEY)
- title
- link (UNIQUE)
- company 
- description
- keywords
- created_date
- is_top_project
- is_endcustomer
- scrape_date

### Matches Table
- id (PRIMARY KEY)
- project_id (FOREIGN KEY)
- title
- link
- company
- description
- keywords
- created_date
- is_top_project
- is_endcustomer
- match_score
- match_debug
- match_date

## Requirements

- Python 3.8+
- See requirements.txt for Python packages

## License

MIT

## Contributing

Pull requests are welcome!
```

Would you like me to add anything specific to the README?
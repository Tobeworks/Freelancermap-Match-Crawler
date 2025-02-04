import pandas as pd
from datetime import datetime
import re

class ProjectProfileMatcher:
    def __init__(self, csv_path):
        self.df = pd.read_csv(csv_path)  # Normale CSV-Einlesung
        self.df['eintragungsdatum'] = pd.to_datetime(self.df['eintragungsdatum'])
        
    def set_profile(self, profile):
        self.profile = profile
        
    def calculate_match_score(self, row):
        score = 0
        debug_info = []
        
        # Keywords Match (50 Punkte)
        if isinstance(row['keywords'], str) and row['keywords'] != 'N/A':
            # Keywords mit Komma trennen
            project_keywords = set(
                kw.strip().lower() 
                for kw in row['keywords'].split(',')
            )
            profile_skills = set(s.lower() for s in self.profile['skills'])
            
            matching_keywords = set()
            for p_kw in project_keywords:
                for skill in profile_skills:
                    if p_kw == skill or skill in p_kw or p_kw in skill:
                        matching_keywords.add(p_kw)
            
            keyword_score = (len(matching_keywords) / max(len(project_keywords), 1)) * 50
            score += keyword_score
            debug_info.append(f"Keywords Score: {keyword_score:.2f}")
            debug_info.append(f"Matching Keywords: {matching_keywords}")
        
        # Beschreibungs-Match (30 Punkte)
        if isinstance(row['beschreibung'], str) and row['beschreibung'] != 'N/A':
            description_lower = row['beschreibung'].lower()
            matching_skills = [skill.lower() for skill in self.profile['skills'] 
                             if skill.lower() in description_lower]
            
            matching_preferred = [kw.lower() for kw in self.profile['preferred_keywords'] 
                                if kw.lower() in description_lower]
            
            desc_score = (len(matching_skills) * 3 + len(matching_preferred) * 2)
            desc_score = min(desc_score, 30)
            score += desc_score
            
            debug_info.append(f"Description Score: {desc_score:.2f}")
            debug_info.append(f"Matching Skills in Description: {matching_skills}")
            debug_info.append(f"Matching Keywords in Description: {matching_preferred}")
        
        # Aktualität (20 Punkte)
        if pd.notnull(row['eintragungsdatum']):
            days_old = (datetime.now() - row['eintragungsdatum']).days
            time_score = max(0, 20 * (1 - days_old/30))
            score += time_score
            debug_info.append(f"Time Score: {time_score:.2f}")
        
        # Ausschlusskriterien
        if isinstance(row['beschreibung'], str):
            excluded_found = [kw for kw in self.profile['excluded_keywords'] 
                            if kw.lower() in row['beschreibung'].lower()]
            if excluded_found:
                score = 0
                debug_info.append(f"Ausgeschlossen wegen: {excluded_found}")
        
        return score, "\n".join(debug_info)
    
    def find_matching_projects(self, min_score=30, sort_by_score=True):
        scores_and_debug = [self.calculate_match_score(row) for _, row in self.df.iterrows()]
        self.df['match_score'] = [score for score, _ in scores_and_debug]
        self.df['match_debug'] = [debug_info for _, debug_info in scores_and_debug]
        
        matching_projects = self.df[self.df['match_score'] >= min_score].copy()
        
        if sort_by_score:
            matching_projects = matching_projects.sort_values(
                ['match_score', 'eintragungsdatum'],
                ascending=[False, False]
            )
        
        return matching_projects

    def get_statistics(self, matching_projects):
        stats = {
            'avg_score': matching_projects['match_score'].mean() if len(matching_projects) > 0 else 0,
            'score_distribution': matching_projects['match_score'].value_counts().sort_index() if len(matching_projects) > 0 else pd.Series(),
            'latest_project': matching_projects['eintragungsdatum'].max() if len(matching_projects) > 0 else None,
            'oldest_project': matching_projects['eintragungsdatum'].min() if len(matching_projects) > 0 else None,
            'skill_distribution': self.skill_statistics if hasattr(self, 'skill_statistics') else {},
            'top_companies': matching_projects['firma'].value_counts().head() if len(matching_projects) > 0 else pd.Series(),
            'total_matches': len(matching_projects)
        }
        return stats

    def export_matches(self, matching_projects, export_path=None):
        if export_path is None:
            export_path = f"matching_projects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        export_columns = [
            'titel',
            'firma',
            'keywords',
            'beschreibung',
            'eintragungsdatum',
            'link',
            'ist_top_projekt',
            'ist_endkundenprojekt',
            'match_debug',
            'match_score'
        ]
        
        export_df = matching_projects[export_columns].sort_values('match_score', ascending=False)
        export_df['eintragungsdatum'] = export_df['eintragungsdatum'].dt.strftime('%Y-%m-%d %H:%M')
        
        # Export mit Semikolon als Trenner
        export_df.to_csv(export_path, index=False, encoding='utf-8', sep=';')
        
        print(f"\nMatching-Ergebnisse wurden exportiert nach: {export_path}")
        print(f"Anzahl unique Matches: {len(export_df)}")
        print(f"Durchschnittlicher Score: {export_df['match_score'].mean():.2f}")
        print("\nTop Firmen:")
        print(export_df['firma'].value_counts().head())
        
        return export_path

if __name__ == "__main__":
    profile = {
        'skills': ['Python', 'JavaScript', 'React', 'Vue', 'MySQL', 'HTML', 'CSS', 'PHP', 'GCP', 'AWS', 'Cloud', 'AI', 'Frontend', 'Vue.js', 'JS'],
        'preferred_keywords': ['Webentwicklung', 'Backend', 'Frontend', 'Fullstack', 'API', 'Wordpress', 'GCP', 'AWS', 'Cloud', 'AI', 'OpenAI'],
        'excluded_keywords': ['SAP', 'Drupal']
    }
    
    matcher = ProjectProfileMatcher('freelancermap_projekte.csv')
    matcher.set_profile(profile)
    matches = matcher.find_matching_projects(min_score=20)
    stats = matcher.get_statistics(matches)
    
    print(f"\nGefundene Matches: {stats['total_matches']}")
    if stats['total_matches'] > 0:
        print(f"Durchschnittlicher Score: {stats['avg_score']:.2f}")
        print("\nTop Matches:")
        print(matches[['titel', 'keywords', 'match_score', 'match_debug']].head())
        export_file = matcher.export_matches(matches)
    else:
        print("\nKeine Matches gefunden. Überprüfen Sie die Matching-Kriterien.")


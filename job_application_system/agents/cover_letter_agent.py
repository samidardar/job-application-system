"""
Agent 3: Cover Letter Agent
Generates ATS-optimized, personalized cover letters for job applications
"""
import re
import os
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

from utils.database import DatabaseManager
from utils.config import get_config
from utils.logging_utils import ActivityLogger

logger = logging.getLogger(__name__)

class CoverLetterAgent:
    """Agent responsible for generating personalized cover letters"""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.config = get_config()
        self.db = db_manager or DatabaseManager(self.config.get_database_path())
        self.activity_logger = ActivityLogger("CoverLetterAgent", self.db)
        
        self.user_profile = self.config.get_user_profile()
        self.output_dir = Path(self.config.get('application.cover_letter.output_dir', 'documents/output'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load templates
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, str]:
        """Load cover letter templates for different languages"""
        templates = {}
        
        for lang in ['fr', 'en']:
            template_path = Path(self.config.get_cover_letter_template_path(lang))
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    templates[lang] = f.read()
            else:
                # Use default template
                templates[lang] = self._get_default_template(lang)
        
        return templates
    
    def _get_default_template(self, lang: str) -> str:
        """Get default template if file doesn't exist"""
        if lang == 'fr':
            return """{user_name}
{user_email}
{user_phone}
{date}

À l'attention du service Recrutement
{company_name}

Objet : Candidature pour le poste de {job_title}

Madame, Monsieur,

Étudiant en {current_study} passionné par {passion_domain}, je suis à la recherche d'une {job_type} pour {period}. Votre offre de {job_title} chez {company_name} a retenu toute mon attention car elle correspond parfaitement à mon projet professionnel.

{skills_paragraph}

{motivation_paragraph}

{company_paragraph}

Je serais ravi de pouvoir échanger avec vous lors d'un entretien pour vous présenter ma motivation et mes compétences. Je reste à votre disposition pour toute information complémentaire.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

{user_name}
"""
        else:  # English
            return """{user_name}
{user_email}
{user_phone}
{date}

Hiring Manager
{company_name}

Subject: Application for {job_title}

Dear Hiring Manager,

I am writing to express my strong interest in the {job_title} position at {company_name}. As a {current_study} student with a passion for {passion_domain}, I am seeking a {job_type} opportunity for {period}.

{skills_paragraph}

{motivation_paragraph}

{company_paragraph}

I would welcome the opportunity to discuss how my background and skills align with your needs. Thank you for considering my application.

Sincerely,

{user_name}
"""
    
    def run(self, job_id: Optional[int] = None) -> Dict[str, str]:
        """
        Generate cover letters for jobs
        If job_id is provided, generate for that specific job
        Otherwise, generate for all shortlisted jobs that don't have cover letters
        """
        self.activity_logger.info("Starting cover letter generation")
        
        generated = []
        
        if job_id:
            # Generate for specific job
            with self.db._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
                job = cursor.fetchone()
                if job:
                    job = dict(job)
                    file_path = self.generate_cover_letter(job)
                    if file_path:
                        generated.append({'job_id': job_id, 'file': file_path})
        else:
            # Generate for all shortlisted jobs without cover letters
            shortlisted = self.db.get_shortlisted_jobs(
                min_score=self.config.get_min_relevance_score(),
                limit=30
            )
            
            for job in shortlisted:
                try:
                    # Check if cover letter already exists
                    with self.db._get_connection() as conn:
                        cursor = conn.execute(
                            "SELECT 1 FROM cover_letters WHERE job_id = ?",
                            (job['id'],)
                        )
                        if cursor.fetchone():
                            continue
                    
                    file_path = self.generate_cover_letter(job)
                    if file_path:
                        generated.append({'job_id': job['id'], 'file': file_path})
                        
                except Exception as e:
                    logger.error(f"Error generating cover letter for job {job['id']}: {e}")
                    self.activity_logger.error(f"Cover letter for job {job['id']}", str(e))
        
        self.activity_logger.info(
            "Cover letter generation complete",
            f"Generated {len(generated)} cover letters"
        )
        
        return {'generated_count': len(generated), 'files': generated}
    
    def generate_cover_letter(self, job: Dict) -> Optional[str]:
        """Generate a cover letter for a specific job"""
        try:
            # Detect language
            language = self._detect_language(job)
            
            # Extract keywords from job
            keywords = self._extract_keywords(job)
            
            # Generate content sections
            skills_paragraph = self._generate_skills_paragraph(job, keywords, language)
            motivation_paragraph = self._generate_motivation_paragraph(job, language)
            company_paragraph = self._generate_company_paragraph(job, language)
            
            # Prepare template variables
            template_vars = self._prepare_template_variables(job, language)
            template_vars['skills_paragraph'] = skills_paragraph
            template_vars['motivation_paragraph'] = motivation_paragraph
            template_vars['company_paragraph'] = company_paragraph
            
            # Generate cover letter
            template = self.templates.get(language, self.templates.get('fr'))
            cover_letter = template.format(**template_vars)
            
            # Optimize for ATS
            cover_letter = self._optimize_for_ats(cover_letter, keywords)
            
            # Save to file
            filename = f"cover_letter_{job['id']}_{language}.txt"
            file_path = self.output_dir / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cover_letter)
            
            # Store in database
            self.db.insert_cover_letter(
                job_id=job['id'],
                file_path=str(file_path),
                language=language,
                content=cover_letter,
                keywords=keywords
            )
            
            logger.info(f"Generated cover letter: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Error generating cover letter: {e}")
            return None
    
    def _detect_language(self, job: Dict) -> str:
        """Detect the language of the job posting"""
        text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
        
        # French indicators
        french_words = ['le', 'la', 'les', 'et', 'pour', 'des', 'une', 'dans', 'est', 'que', 
                       'alternance', 'stage', 'poste', 'profil', 'compétences', 'mission']
        
        # English indicators  
        english_words = ['the', 'and', 'for', 'with', 'are', 'you', 'will', 'job', 'position',
                        'skills', 'requirements', 'experience', 'work']
        
        french_count = sum(1 for word in french_words if f' {word} ' in f' {text.lower()} ')
        english_count = sum(1 for word in english_words if f' {word} ' in f' {text.lower()} ')
        
        # Check location
        location = (job.get('location') or '').lower()
        if any(loc in location for loc in ['france', 'paris', 'lyon', 'marseille', 'bordeaux']):
            french_count += 3
        
        if french_count > english_count:
            return 'fr'
        else:
            return 'en'
    
    def _extract_keywords(self, job: Dict) -> List[str]:
        """Extract important keywords from job description"""
        text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
        text = text.lower()
        
        # Technical skills to look for
        tech_keywords = [
            'python', 'r', 'sql', 'machine learning', 'deep learning', 'tensorflow', 
            'pytorch', 'scikit-learn', 'pandas', 'numpy', 'data analysis', 'statistics',
            'big data', 'spark', 'hadoop', 'aws', 'azure', 'gcp', 'docker', 'kubernetes',
            'nlp', 'computer vision', 'reinforcement learning', 'time series',
            'quantitative', 'finance', 'trading', 'risk', 'portfolio', 'derivatives'
        ]
        
        found_keywords = []
        for keyword in tech_keywords:
            if keyword in text:
                found_keywords.append(keyword)
        
        # Limit to top keywords
        return found_keywords[:15]
    
    def _prepare_template_variables(self, job: Dict, language: str) -> Dict[str, str]:
        """Prepare variables for template formatting"""
        user = self.user_profile
        education = user.get('education', {})
        current_study = education.get('current', {}).get('degree', 'Data Science')
        
        # Get job type
        job_type = job.get('job_type') or ('Alternance' if language == 'fr' else 'Internship')
        
        # Period
        period = "l'année universitaire 2024-2026" if language == 'fr' else "the 2024-2026 academic year"
        
        # Passion domain
        passion_domain = "l'intelligence artificielle et la data science" if language == 'fr' else "AI and data science"
        if 'quant' in job.get('title', '').lower():
            passion_domain = "la finance quantitative" if language == 'fr' else "quantitative finance"
        
        return {
            'user_name': user.get('full_name', 'Sami'),
            'user_email': user.get('email', ''),
            'user_phone': user.get('phone', ''),
            'date': datetime.now().strftime('%d/%m/%Y'),
            'company_name': job.get('company', ''),
            'job_title': job.get('title', ''),
            'job_type': job_type,
            'current_study': current_study,
            'period': period,
            'passion_domain': passion_domain
        }
    
    def _generate_skills_paragraph(self, job: Dict, keywords: List[str], language: str) -> str:
        """Generate paragraph highlighting relevant skills"""
        user_skills = self.user_profile.get('skills', {}).get('technical', [])
        
        # Match user skills with job keywords
        matched_skills = []
        for skill in user_skills[:5]:  # Top 5 skills
            skill_lower = skill.lower()
            if any(skill_lower in kw or kw in skill_lower for kw in keywords):
                matched_skills.append(skill)
        
        if not matched_skills:
            matched_skills = user_skills[:3]
        
        if language == 'fr':
            if matched_skills:
                skills_text = ", ".join(matched_skills[:-1]) + f" et {matched_skills[-1]}" if len(matched_skills) > 1 else matched_skills[0]
                return f"Au cours de ma formation, j'ai développé des compétences solides en {skills_text}. Je maîtrise également les outils et technologies essentiels pour ce poste."
            else:
                return "Ma formation m'a permis d'acquérir une solide base technique et une méthodologie rigoureuse pour aborder les problématiques data."
        else:
            if matched_skills:
                skills_text = ", ".join(matched_skills[:-1]) + f" and {matched_skills[-1]}" if len(matched_skills) > 1 else matched_skills[0]
                return f"Throughout my studies, I have developed strong skills in {skills_text}. I am also proficient in the essential tools and technologies required for this position."
            else:
                return "My academic background has provided me with a solid technical foundation and rigorous methodology for tackling data challenges."
    
    def _generate_motivation_paragraph(self, job: Dict, language: str) -> str:
        """Generate motivation paragraph"""
        title = job.get('title', '')
        
        if language == 'fr':
            if 'quant' in title.lower():
                return "Passionné par la finance quantitative et les mathématiques appliquées, je suis particulièrement intéressé par l'utilisation des modèles statistiques et du machine learning pour résoudre des problématiques financières complexes."
            elif 'deep learning' in title.lower() or 'nlp' in title.lower():
                return "Fasciné par les avancées récentes en intelligence artificielle, je souhaite approfondir mes connaissances en deep learning et contribuer à des projets innovants dans ce domaine."
            else:
                return "Passionné par l'analyse de données et le machine learning, je suis motivé à l'idée de mettre mes compétences au service de projets concrets et de continuer à apprendre auprès de professionnels expérimentés."
        else:
            if 'quant' in title.lower():
                return "Passionate about quantitative finance and applied mathematics, I am particularly interested in using statistical models and machine learning to solve complex financial challenges."
            elif 'deep learning' in title.lower() or 'nlp' in title.lower():
                return "Fascinated by recent advances in artificial intelligence, I am eager to deepen my knowledge in deep learning and contribute to innovative projects in this field."
            else:
                return "Passionate about data analysis and machine learning, I am motivated to apply my skills to real-world projects and continue learning from experienced professionals."
    
    def _generate_company_paragraph(self, job: Dict, language: str) -> str:
        """Generate company-specific paragraph"""
        company = job.get('company', '')
        description = job.get('description', '')
        
        # Extract company values or projects from description if available
        values = []
        if 'innovation' in description.lower():
            values.append('innovation' if language == 'en' else 'innovation')
        if 'research' in description.lower() or 'recherche' in description.lower():
            values.append('research' if language == 'en' else 'recherche')
        if 'team' in description.lower() or 'équipe' in description.lower():
            values.append('teamwork' if language == 'en' else 'travail d\'équipe')
        
        if language == 'fr':
            if values:
                values_text = ", ".join(values)
                return f"Ce qui m'attire particulièrement chez {company}, c'est votre engagement envers l'{values_text} et votre volonté de repousser les limites de ce qui est possible. Je suis convaincu que mon profil et ma motivation correspondront à vos attentes."
            else:
                return f"Je suis particulièrement intéressé par l'opportunité de rejoindre {company} et de contribuer à vos projets ambitieux. Je suis convaincu que mon profil et ma motivation correspondront à vos attentes."
        else:
            if values:
                values_text = ", ".join(values)
                return f"What particularly attracts me to {company} is your commitment to {values_text} and your drive to push the boundaries of what is possible. I am confident that my profile and motivation will meet your expectations."
            else:
                return f"I am particularly interested in the opportunity to join {company} and contribute to your ambitious projects. I am confident that my profile and motivation will meet your expectations."
    
    def _optimize_for_ats(self, cover_letter: str, keywords: List[str]) -> str:
        """Optimize cover letter for ATS (Applicant Tracking Systems)"""
        # Ensure keywords are naturally integrated
        for keyword in keywords[:5]:  # Top 5 keywords
            if keyword.lower() not in cover_letter.lower():
                # Find a natural place to add it
                # For now, we'll skip adding to avoid awkward sentences
                pass
        
        # Remove special characters that might confuse ATS
        cover_letter = re.sub(r'[^\w\s\-\.\@\,\(\)\'\:\/\n]', '', cover_letter)
        
        # Ensure proper formatting
        lines = cover_letter.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        
        return '\n\n'.join(lines)
    
    def get_generated_letters(self, job_id: Optional[int] = None) -> List[Dict]:
        """Get list of generated cover letters"""
        with self.db._get_connection() as conn:
            if job_id:
                cursor = conn.execute(
                    "SELECT * FROM cover_letters WHERE job_id = ? ORDER BY generated_at DESC",
                    (job_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM cover_letters ORDER BY generated_at DESC LIMIT 50"
                )
            
            return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    agent = CoverLetterAgent()
    results = agent.run()
    print(f"Cover letter generation complete: {results}")

# Job Application System - Project Structure Summary

## 📁 Complete File Tree

```
job_application_system/
├── README.md                          # Documentation principale
├── requirements.txt                   # Dépendances Python
├── orchestrator.py                    # Orchestrateur principal
├── run_daily.sh                       # Script quotidien exécutable
├── test_system.py                     # Script de test
├── .env.example                       # Exemple de variables d'environnement
│
├── agents/                            # AGENTS (4 agents)
│   ├── __init__.py
│   ├── scraping_agent.py             # Agent 1: Scraping (LinkedIn, Indeed, WTTJ)
│   ├── analysis_agent.py             # Agent 2: Analyse et scoring de pertinence
│   ├── cover_letter_agent.py         # Agent 3: Génération lettres de motivation
│   └── application_agent.py          # Agent 4: Soumission candidatures
│
├── config/                            # CONFIGURATION
│   ├── __init__.py
│   ├── config.yaml                   # Configuration principale (à personnaliser)
│   └── crontab.txt                   # Configuration cron d'exemple
│
├── dashboard/                         # DASHBOARD WEB
│   ├── __init__.py
│   ├── app.py                        # Application Flask (backend API)
│   ├── templates/
│   │   └── index.html                # Interface web principale
│   └── static/
│       ├── css/
│       │   └── styles.css            # Styles du dashboard
│       └── js/
│           └── dashboard.js          # JavaScript du dashboard
│
├── database/                          # BASE DE DONNÉES
│   ├── __init__.py
│   ├── schema.sql                    # Schéma SQLite
│   └── backups/                      # Sauvegardes automatiques
│       └── .gitkeep
│
├── documents/                         # DOCUMENTS
│   ├── __init__.py
│   ├── templates/                    # Templates lettres
│   │   ├── __init__.py
│   │   ├── cover_letter_fr_template.txt   # Template français
│   │   └── cover_letter_en_template.txt   # Template anglais
│   └── output/                       # Lettres générées (output)
│       └── .gitkeep
│
├── utils/                             # UTILITAIRES
│   ├── __init__.py
│   ├── database.py                   # Gestion base de données
│   ├── config.py                     # Chargement configuration
│   ├── logging_utils.py              # Logging et journalisation
│   └── anti_detection.py             # Anti-détection et human-like behavior
│
└── logs/                              # LOGS
    └── .gitkeep
```

## 🔢 Statistiques du Projet

| Catégorie | Fichiers | Lignes de code approx |
|-----------|----------|----------------------|
| Agents (4) | 4 | ~2,500 |
| Dashboard | 3 | ~1,200 |
| Utils | 4 | ~1,400 |
| Configuration | 2 | ~500 |
| Documentation | 1 | ~350 |
| **Total** | **~20** | **~6,000** |

## 🎯 Architecture du Système

### Flux de données:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Scraping Agent │────▶│ Analysis Agent  │────▶│  Cover Letter   │
│   (Agent 1)     │     │   (Agent 2)     │     │   (Agent 3)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
   ┌──────────┐           ┌──────────┐           ┌──────────┐
   │  Jobs    │           │  Score   │           │  Lettre  │
   │ Scrapées │           │  1-10    │           │   LM     │
   └──────────┘           └──────────┘           └──────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │ Application Agent│
                                               │   (Agent 4)     │
                                               └─────────────────┘
                                                        │
                                                        ▼
                                               ┌──────────┐
                                               │Candidature│
                                               │  Envoyée  │
                                               └──────────┘
```

### Workflow Quotidien:

```
08:00  ▶  Scraping des offres (LinkedIn, Indeed, WTTJ)
       │
08:30  ▶  Analyse et scoring (pertinence 1-10)
       │
08:45  ▶  Génération lettres de motivation
       │
09:00  ▶  Soumission candidatures (avec limites quotidiennes)
       │
18:00  ▶  Rapport quotidien et notifications
```

## 🔧 Composants Clés

### 1. Anti-Ban Strategy
- Délais aléatoires entre requêtes (2-8s)
- Rotation User-Agent
- Limites de session (30 requêtes max)
- Pauses entre sessions (5 min)
- Limites quotidiennes (30 candidatures max)

### 2. Scoring de Pertinence (1-10)
- Keywords matching (4 pts max)
- Skills matching (3 pts max)
- Type de contrat (1 pt)
- Niveau d'expérience (1 pt)
- Localisation (0.5 pt)
- Récence de l'offre (0.5 pt)
- Pénalités exclusions (-2 pts)

### 3. Dashboard Features
- Vue pipeline en temps réel
- Statistiques quotidiennes
- Graphiques d'activité
- Top opportunités
- Suivi des candidatures
- Relances à effectuer
- Paramètres configurables

## 🚀 Démarrage Rapide

```bash
# 1. Installation
cd job_application_system
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configuration
nano config/config.yaml  # Personnalisez vos infos

# 3. Test
python test_system.py

# 4. Premier run (dry-run)
python orchestrator.py full

# 5. Dashboard
python dashboard/app.py
# Ouvrir http://localhost:5000

# 6. Automatisation (cron)
crontab config/crontab.txt
```

## 📊 Tables de la Base de Données

| Table | Description |
|-------|-------------|
| `jobs` | Offres d'emploi scrapées |
| `applications` | Candidatures envoyées |
| `cover_letters` | Lettres de motivation générées |
| `activity_log` | Journal des activités |
| `platform_stats` | Statistiques par plateforme |
| `companies` | Entreprises suivies |
| `user_profile` | Profil de Sami |
| `settings` | Paramètres système |
| `scraping_sessions` | Sessions de scraping |

## 🎨 Personnalisation

### Pour adapter le système à vos besoins:

1. **Modifier `config/config.yaml`**:
   - Vos informations personnelles
   - Vos compétences
   - Vos critères de recherche
   - Vos lieux préférés

2. **Adapter les templates**:
   - `documents/templates/cover_letter_fr_template.txt`
   - `documents/templates/cover_letter_en_template.txt`

3. **Ajouter votre CV**:
   - `documents/cv_sami.pdf`
   - `documents/cv_sami_en.pdf` (optionnel)

## 🔒 Sécurité

- Mode dry-run par défaut
- Limites de débit configurables
- Rotation d'User-Agent
- Respect des robots.txt
- Gestion de sessions

## 📝 Notes

Ce système est conçu pour:
- Automatiser la recherche d'alternance en Data Science/ML/AI/Quant
- Générer des lettres de motivation personnalisées
- Suivre les candidatures en cours
- Respecter les limites des plateformes

**Important**: Toujours vérifier les candidatures avant envoi final!

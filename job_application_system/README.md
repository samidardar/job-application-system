# Job Application System - Setup Instructions

Système multi-agents automatisé pour la recherche et candidature à des offres d'alternance en Data Science / ML / AI / Quant.

## 📁 Structure du Projet

```
job_application_system/
├── agents/
│   ├── scraping_agent.py      # Agent 1: Scraping des offres
│   ├── analysis_agent.py      # Agent 2: Analyse et scoring
│   ├── cover_letter_agent.py  # Agent 3: Génération lettres
│   └── application_agent.py   # Agent 4: Soumission candidatures
├── config/
│   └── config.yaml            # Configuration du système
├── dashboard/
│   ├── app.py                 # Application Flask
│   ├── templates/
│   │   └── index.html         # Interface web
│   └── static/
│       ├── css/
│       │   └── styles.css     # Styles du dashboard
│       └── js/
│           └── dashboard.js   # JavaScript du dashboard
├── database/
│   └── schema.sql             # Schéma de la base de données
├── documents/
│   ├── templates/             # Templates de lettres
│   └── output/                # Lettres générées
├── utils/
│   ├── database.py            # Gestion base de données
│   ├── config.py              # Chargement configuration
│   ├── logging_utils.py       # Utilitaires de logging
│   └── anti_detection.py      # Anti-détection
├── logs/                      # Fichiers de log
├── orchestrator.py            # Orchestrateur principal
├── requirements.txt           # Dépendances Python
└── README.md                  # Ce fichier
```

## 🚀 Installation

### 1. Cloner/Extraire le projet

```bash
cd job_application_system
```

### 2. Créer un environnement virtuel (recommandé)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer le système

Éditer `config/config.yaml` pour personnaliser :

- **Informations personnelles** (section `user`)
  - `full_name`: Votre nom complet
  - `email`: Votre email
  - `phone`: Votre téléphone
  - `linkedin_url`, `github_url`, `portfolio_url`: Vos liens

- **Compétences** (section `user.skills`)
  - Ajoutez/modifiez vos compétences techniques et soft skills

- **Formation** (section `user.education`)
  - Votre formation actuelle et précédente

- **Lieux préférés** (section `user.locations`)
  - Villes ou régions où vous cherchez

- **Mots-clés de recherche** (section `search.keywords`)
  - Ajustez selon vos intérêts

- **Plateformes** (section `platforms`)
  - Activez/désactivez les plateformes
  - Modifiez les URLs de recherche

### 5. Initialiser la base de données

```bash
python -c "from utils.database import DatabaseManager; db = DatabaseManager()"
```

### 6. Ajouter votre CV

Placez votre CV dans `documents/` :
- `cv_sami.pdf` (version française)
- `cv_sami_en.pdf` (version anglaise, optionnel)

## 🎯 Utilisation

### Commandes disponibles

#### Lancer le workflow complet (dry-run par défaut)
```bash
python orchestrator.py full
```

#### Lancer avec véritable soumission de candidatures
```bash
python orchestrator.py full --no-dry-run
```

#### Lancer uniquement le scraping
```bash
python orchestrator.py scrape
```

#### Lancer uniquement l'analyse
```bash
python orchestrator.py analyze
```

#### Générer uniquement les lettres de motivation
```bash
python orchestrator.py letters
```

#### Soumettre uniquement les candidatures
```bash
python orchestrator.py apply
# ou
python orchestrator.py apply --no-dry-run
```

#### Générer un rapport
```bash
python orchestrator.py report
```

### Démarrer le Dashboard Web

```bash
python dashboard/app.py
```

Puis ouvrir http://localhost:5000 dans votre navigateur.

## ⏰ Configuration Cron (Automatisation quotidienne)

### Option 1: Crontab Linux/Mac

Éditer votre crontab :
```bash
crontab -e
```

Ajouter ces lignes :

```bash
# Job Application System - Daily Schedule

# Scraping à 8h00
0 8 * * * cd /chemin/vers/job_application_system && /chemin/vers/venv/bin/python orchestrator.py scrape >> logs/cron.log 2>&1

# Analyse à 8h30
30 8 * * * cd /chemin/vers/job_application_system && /chemin/vers/venv/bin/python orchestrator.py analyze >> logs/cron.log 2>&1

# Génération lettres à 8h45
45 8 * * * cd /chemin/vers/job_application_system && /chemin/vers/venv/bin/python orchestrator.py letters >> logs/cron.log 2>&1

# Candidatures à 9h00 (dry-run par défaut, changez pour --no-dry-run avec précaution)
0 9 * * * cd /chemin/vers/job_application_system && /chemin/vers/venv/bin/python orchestrator.py apply >> logs/cron.log 2>&1

# Rapport quotidien à 18h00
0 18 * * * cd /chemin/vers/job_application_system && /chemin/vers/venv/bin/python orchestrator.py report >> logs/cron.log 2>&1

# Nettoyage hebdomadaire (dimanche à 2h00)
0 2 * * 0 cd /chemin/vers/job_application_system && /chemin/vers/venv/bin/python -c "from utils.database import DatabaseManager; db = DatabaseManager(); db.backup_database()" >> logs/cron.log 2>&1
```

### Option 2: Script de lancement

Créer `run_daily.sh` :

```bash
#!/bin/bash

PROJECT_DIR="/chemin/vers/job_application_system"
PYTHON="$PROJECT_DIR/venv/bin/python"
LOG_FILE="$PROJECT_DIR/logs/daily_$(date +%Y%m%d).log"

cd "$PROJECT_DIR"

echo "=== Job Application System - $(date) ===" >> "$LOG_FILE"

echo "[1/4] Scraping..." >> "$LOG_FILE"
$PYTHON orchestrator.py scrape >> "$LOG_FILE" 2>&1

echo "[2/4] Analyzing..." >> "$LOG_FILE"
$PYTHON orchestrator.py analyze >> "$LOG_FILE" 2>&1

echo "[3/4] Generating cover letters..." >> "$LOG_FILE"
$PYTHON orchestrator.py letters >> "$LOG_FILE" 2>&1

echo "[4/4] Applying..." >> "$LOG_FILE"
$PYTHON orchestrator.py apply >> "$LOG_FILE" 2>&1

echo "=== Completed at $(date) ===" >> "$LOG_FILE"
```

Rendre exécutable :
```bash
chmod +x run_daily.sh
```

Puis dans crontab :
```bash
0 9 * * * /chemin/vers/job_application_system/run_daily.sh
```

## ⚙️ Configuration Anti-Ban

Le système inclut plusieurs mécanismes anti-détection :

1. **Délais aléatoires** entre les requêtes (configurable)
2. **Rotation des User-Agents**
3. **Limites de session** (pauses entre les sessions)
4. **Limites quotidiennes** de candidatures

### Paramètres importants dans `config.yaml` :

```yaml
anti_detection:
  delay_min: 3           # Délai minimum en secondes
  delay_max: 8           # Délai maximum en secondes
  max_requests_per_session: 30
  session_break_duration: 300  # 5 minutes

application:
  daily_limit: 30        # Maximum de candidatures par jour
  auto_apply: false      # Ne pas appliquer automatiquement par défaut
```

## 📝 Notes importantes

### Sur les plateformes supportées

- **LinkedIn**: Supporte LinkedIn Easy Apply (nécessite authentification)
- **Indeed**: Scraping des offres publiques
- **Welcome to the Jungle**: API et scraping

### Sécurité et respect des ToS

1. **Respectez les limites** - Ne modifiez pas les délais pour aller plus vite
2. **Vérifiez les candidatures** - Mode dry-run par défaut
3. **Personnalisez les lettres** - Relisez avant envoi
4. **Usage responsable** - Respectez les conditions d'utilisation des plateformes

### Pour aller plus loin

#### Intégration avec un LLM

Pour des lettres de motivation plus sophistiquées, vous pouvez intégrer un LLM :

```python
# Dans cover_letter_agent.py, remplacez les méthodes de génération
# par des appels à l'API OpenAI ou autre
```

#### Notifications

Pour recevoir des notifications (email/Telegram/Slack), ajoutez dans `utils/notifications.py` :

```python
import smtplib
# ou
import requests  # pour Telegram/Slack webhooks
```

#### Sauvegardes

Les sauvegardes automatiques de la base de données sont configurées dans le cron hebdomadaire.

## 🔧 Dépannage

### Problème: Aucune offre trouvée
- Vérifiez les URLs de recherche dans `config.yaml`
- Vérifiez votre connexion Internet
- Consultez les logs dans `logs/system.log`

### Problème: Score de pertinence trop bas
- Ajustez les mots-clés dans `config.yaml`
- Vérifiez que vos compétences sont bien listées
- Baissez `min_relevance_score` temporairement

### Problème: Rate limiting / Bannissement
- Augmentez les délais dans `config.yaml`
- Réduisez `daily_limit`
- Augmentez `session_break_duration`
- Attendez 24h avant de relancer

## 📊 Accès aux données

La base SQLite est accessible directement :

```bash
sqlite3 database/job_application.db
```

Quelques requêtes utiles :

```sql
-- Voir les offres les plus pertinentes
SELECT title, company, relevance_score, platform 
FROM jobs 
WHERE relevance_score > 7 
ORDER BY relevance_score DESC 
LIMIT 10;

-- Voir les candidatures par statut
SELECT status, COUNT(*) 
FROM applications 
GROUP BY status;

-- Voir l'activité récente
SELECT * FROM activity_log 
ORDER BY created_at DESC 
LIMIT 20;
```

## 🆘 Support

En cas de problème :
1. Consultez les logs dans `logs/`
2. Vérifiez la configuration
3. Testez avec `python orchestrator.py full` (dry-run)

---

**Note**: Ce système est conçu pour aider dans la recherche d'emploi, mais ne remplace pas la personnalisation manuelle des candidatures pour les postes les plus importants.

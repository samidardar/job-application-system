# Postulio 🎯

**Plateforme IA d'automatisation de candidatures pour le marché français**

> Chaque matin à 8h, Postulio scrape les offres des 24h dernières sur LinkedIn, Indeed et Welcome to the Jungle, génère un CV et une lettre de motivation sur mesure pour chaque offre pertinente, et soumet automatiquement les candidatures — le tout tracké dans un dashboard en temps réel.

## Stack technique

| Layer | Tech |
|---|---|
| Backend | FastAPI 0.110 (Python 3.12, async) |
| Frontend | Next.js 14 App Router + TailwindCSS + shadcn/ui |
| Database | PostgreSQL 16 + SQLAlchemy async + Alembic |
| Queue | Celery 5 + Redis 7 + Celery Beat |
| IA | Claude claude-sonnet-4-6 (Anthropic SDK) |
| Scraping | jobspy + Playwright |
| PDF | WeasyPrint |
| Auth | JWT + bcrypt |
| Deploy | Docker Compose |

## Démarrage rapide

### Prérequis
- Docker & Docker Compose
- Clé API Anthropic

### Installation

```bash
# 1. Cloner le repo
git clone <repo-url>
cd postulio

# 2. Configurer l'environnement
cp .env.example .env
# Éditer .env et ajouter votre ANTHROPIC_API_KEY

# 3. Démarrer tous les services
docker-compose up -d

# 4. Appliquer les migrations
docker-compose exec backend alembic upgrade head

# 5. Accéder à l'application
# Frontend: http://localhost:3000
# API docs: http://localhost:8000/docs
```

## Flux du pipeline quotidien (8h00)

```
1. Scraping Agent    → LinkedIn + Indeed + WTTJ (24h)
2. Matching Agent    → Score IA 0-100, filtre >= 70
3. CV Optimizer      → CV taillé ATS par offre (Claude)
4. Cover Letter      → Lettre de motivation FR (Claude)
5. Application Agent → Soumission auto (Playwright)
6. Follow-up Agent   → Relance J+7 si pas de réponse
```

## Architecture

```
postulio/
├── backend/          # FastAPI + agents IA + Celery workers
├── frontend/         # Next.js 14 dashboard
├── docker-compose.yml
└── .env.example
```

## API Documentation

Swagger UI disponible sur http://localhost:8000/docs après démarrage.

## Agents IA

| Agent | Rôle | Modèle |
|---|---|---|
| Scraping | Collecte des offres 24h | jobspy + Playwright |
| Matching | Score pertinence 0-100 | claude-sonnet-4-6 |
| CV Optimizer | CV taillé ATS | claude-sonnet-4-6 |
| Cover Letter | Lettre de motivation FR | claude-sonnet-4-6 |
| Application | Soumission formulaires | Playwright + Claude |
| Follow-up | Relance J+7 | claude-sonnet-4-6 |

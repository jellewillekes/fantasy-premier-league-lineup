# FPL Lineup Lab (2025/26)

A lightweight, reproducible repo to fetch **current-season** Premier League player data from free public sources (Understat + optional FotMob), analyze FPL-relevant metrics, and optimize your **Fantasy Premier League** starting XI.

> ⚠️ Data is gathered from public endpoints for personal use. Respect each site's Terms of Service.

## Quickstart

### 1) Create the repo on GitHub
- Go to **github.com → New repository** → name: `fpl-lineup-lab`
- Choose **Public** (recommended) → click **Create repository**.

### 2) Initialize locally and push
```bash
git init
git add .
git commit -m "bootstrap FPL lineup lab"
git branch -M main
git remote add origin https://github.com/<you>/fpl-lineup-lab.git
git push -u origin main
```

### 3) Create a Python environment
```bash
# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 4) Install dependencies
```bash
pip install -r requirements.txt
```

### 5) Run Jupyter and open the notebook
```bash
jupyter notebook
# open notebooks/01_build_lineup.ipynb
```

## Data sources

- **Understat** (free): xG, xA, shots, key passes, minutes, goals, assists.
- **FotMob** (free, unofficial endpoint): quick leaderboards for SoT, saves, clean sheets, etc.

## Project layout

```
src/fpl_data/
  understat.py     # fetch + normalize Understat EPL players (this season)
  fotmob.py        # optional helper to fetch quick leaderboards
notebooks/
  01_build_lineup.ipynb  # end-to-end analysis & lineup builder
data/
  raw/             # downloaded json/csv (gitignored)
  processed/       # cleaned datasets (gitignored)
.github/workflows/
  fetch.yml        # (optional) scheduled data refresh
```

## VS Code tips
- Open the folder in VS Code → it will detect the virtualenv `.venv/`.
- Install the **Python** and **Jupyter** extensions.
- Select the `.venv` interpreter (⌘⇧P / Ctrl+Shift+P → "Python: Select Interpreter").

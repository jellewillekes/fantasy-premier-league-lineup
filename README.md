# FPL Lineup (25/26)

A reproducible research and optimization project to **analyze and build Fantasy Premier League (FPL)** teams for the 2025/26 season.
The repository combines **official FPL API data** and **football-data.org** (for match results and standings) to estimate expected points (EP), evaluate team strength, and construct the **optimal lineup, wildcard, and transfers**.

> Data collected from public sources for personal, non-commercial analysis.

---

## Quickstart

### 1. Clone & set up the environment
```bash
git clone https://github.com/<you>/fpl-lineup-lab.git
cd fpl-lineup-lab

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up your football-data.org token
```bash
export FOOTBALL_DATA_ORG_TOKEN="token"
```

### 3. Run the base weekly optimizer
```bash
python run_week.py
```

This builds the **FPL universe**, computes expected points per player and gameweek, estimates team strengths, selects a squad, and suggests:
- The **best XI** (with captain/vice)
- The **optimal transfer move**

---

## How it works

### Data sources
- **FPL API** — player stats, fixtures, form, cost, selection %.
- **football-data.org API** — current Premier League standings & match results for team strength estimation.

### Core data pipeline (`src/fpl_engine/`)
| Module | Purpose |
|--------|----------|
| `fpl_api.py` | Pulls bootstrap & fixtures data from FPL. |
| `fdorg_api.py` | Queries football-data.org standings & results. |
| `team_strength.py` | Estimates attacking/defensive strength from recent form. |
| `minutes.py` | Predicts expected minutes and probability of starts. |
| `rates.py` | Builds per-fixture expected events (xG, xA, CS, saves). |
| `ep.py` | Converts expected events → expected FPL points (Poisson model). |
| `lineup.py` | Optimizes starting XI and captaincy. |
| `transfers.py` | Suggests best 1FT/2FT moves given constraints. |
| `optimize_squad.py` | Wildcard optimization via linear programming (Pulp). |

### Expected Points (EP) Model
For each player and fixture:
1. **Minutes** predicted using historical starts, rotation risk, and rest period.
2. **Expected goals (xG) and assists (xA)** estimated by role-based rates (`event_rates_for_fixture`).
3. **Clean sheets (CS)** derived via Poisson probability of 0 goals conceded.
4. **Bonus points** approximated via a heuristic from xG+xA+saves.
5. **Total EP** = weighted sum of expected points across next N gameweeks.

### Team Strength Model
- Uses `football-data.org` results to estimate home/away attacking and defensive multipliers.
- Adjusts expected xG/xA rates per fixture based on relative team strengths.

### Optimization Strategy
| Scenario | Method | Constraints |
|-----------|---------|-------------|
| **Wildcard (best 15)** | Integer Linear Programming (Pulp) | Budget ≤ £100m, 15 players, 2 GKP/5 DEF/5 MID/3 FWD, ≤3 per club |
| **Lineup** | Mean–variance optimization | Picks starting XI + captain/vice |
| **Transfers** | Beam search (1–2 FTs) | Evaluates horizon EP gain per move |

---

## Analysis Notebooks (Python Scripts)

Each analysis script can be run directly — no Jupyter required.

### Exploratory Data Analysis
```bash
python notebooks/eda.py
```
**Purpose:**
Explore top FPL assets by expected points, value (EP/£), form, xGI/90, and defensive strength.

Outputs include:
- Top 20 by horizon EP
- Best value players
- Form leaders per position
- Attackers with highest xGI/90
- Defenders combining low xGC/90 with strong EP

---

### Team Analysis
```bash
python notebooks/team_analysis.py --names "Areola, Martinez, Senesi, Ruben Dias, Gabriel, Pedro Porro, Romero, Mac Allister, Bruno Fernandes, Bruno Guimaraes, Caicedo, Enzo, Joao Pedro, Erling Haaland, Piroe" --save
```

**Purpose:**
Analyze your personal team’s expected performance over the next 4 GWs.

Outputs include:
- Squad summary with cost, form, points per game
- Expected points for next N GWs
- Next fixtures for your teams
- Optimal XI, captain, vice, and bench
- Position-wise expected points breakdown

Once saved, your team is stored under:
```
data/my_team.json
```
You can run later without `--names`.

---

### Quick Optimizations
```bash
python notebooks/quick_opts.py --budget 100.0 --myteam "Areola, Martinez, Senesi, Ruben Dias, Gabriel, Pedro Porro, Romero, Mac Allister, Bruno Fernandes, Bruno Guimaraes, Caicedo, Enzo, Joao Pedro, Erling Haaland, Piroe"
```

**Purpose:**
Run fast optimizations to:
- Compute the **Wildcard (best 15)** within budget.
- Show the **best XI and captain** for the next GW.
- Suggest **1 transfer** from your current team that maximizes horizon EP.

---

## How We Select a Team

1. **Gather Data:**
   - Pull player-level stats from the live FPL API.
   - Get league standings and results from football-data.org.

2. **Estimate Expected Points (EP):**
   - Model each fixture with team strength and player-level attack/defense contributions.
   - Adjust by expected minutes and variance.

3. **Optimize Squad:**
   - Wildcard optimization via linear programming.
   - Lineup optimization using mean–variance utility.
   - Transfers optimized for EP gain, respecting rules.

4. **Evaluate Performance:**
   - Compare horizon EP with actual form and points.
   - Track per-position contributions and opponent difficulty.

---

## Project Layout

```
src/fpl_engine/
    fpl_api.py
    fdorg_api.py
    team_strength.py
    minutes.py
    roles.py
    rates.py
    bonus.py
    ep.py
    lineup.py
    transfers.py
    optimize_squad.py

notebooks/
    common.py           # shared data + utilities
    eda.py              # exploratory data analysis
    team_analysis.py    # analyze your own team
    quick_opts.py       # run wildcard & transfer optimizations

data/
    my_team.json        # saved team
    raw/                # downloaded FPL + FD.org data (gitignored)
```

---

## Example Workflow

```bash
# 1. Run exploratory data analysis
python notebooks/eda.py

# 2. Save your current team and analyze it
python notebooks/team_analysis.py --names "Areola, Martinez, Ruben Dias, Haaland, ..." --save

# 3. Generate wildcard and best XI
python notebooks/quick_opts.py --budget 100

# 4. Run weekly refresh
python run_week.py
```

---

## Notes
- Works on free APIs (no scraping, no credentials required).
- Models are simple, interpretable, and fast.
- Designed for experimentation and extension. (xGI, ICT, custom ML forecasts).

---

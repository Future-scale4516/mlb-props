# MLB Prop Analyser v2 — Auto-Fetch with Fangraphs

Fully automated daily MLB prop scoring app.

## What auto-loads
- MLB schedule and probable pitchers (MLB Stats API)
- Advanced batting stats: AVG, OBP, ISO, wRC+, K%, HardHit%, Barrel% (Fangraphs via pybaseball - cached 24hrs)
- Live weather per ballpark (Open-Meteo, no API key needed)
- Confirmed lineups when posted (MLB live game feed)

## Deploy on Streamlit Cloud (mobile-friendly)
1. Create a GitHub repo and upload app.py, requirements.txt, README.md
2. Go to share.streamlit.io -> New App -> connect repo -> Deploy
3. Bookmark the URL on your phone

## Run locally
pip install -r requirements.txt
streamlit run app.py

## Notes on Fangraphs stats
- pybaseball scrapes Fangraphs legally, but may be rate-limited.
- Stats are cached for 24 hours so only one fetch per day.
- If Fangraphs is unavailable the app silently falls back to MLB API basic stats (AVG, OBP, OPS).

## Scoring model inputs
When Fangraphs is available: AVG, OBP, ISO, wRC+, K%, HardHit%, Barrel%
Fallback: AVG, OBP, SLG from MLB Stats API
Both factor in: pitcher ERA, WHIP, HR/9, K/9 + park factor + weather + batting order position

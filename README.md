# MLB Prop Analyser v2

## Key fix
Uses `https://statsapi.mlb.com/api/v1/stats?playerPool=ALL` — returns all 500+ MLB batters
in a single call matched by player_id (not name), so no player is ever missed.

## Deploy
Upload app.py + requirements.txt + README.md to GitHub repo, deploy on share.streamlit.io

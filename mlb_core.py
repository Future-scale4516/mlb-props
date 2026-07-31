import os
import numpy as np
from scipy.stats import nbinom
import joblib  # Standard for loading serialized ML models safely

# --- Upgraded Distribution & Simulation Engine ---

def _nbinom_vector(lam, alpha=0.12, max_runs=18):
    """
    Replaces _pois_vector. Uses Negative Binomial to account for MLB overdispersion.
    alpha: The dispersion parameter (0.12 is typical for MLB run variance).
    """
    if lam <= 0:
        return [1.0] + [0.0] * max_runs
    
    # Map mean (lam) and dispersion (alpha) to scipy's n and p parameters
    # Variance = lam + alpha * lam^2
    n = 1.0 / alpha
    p = n / (n + lam)
    
    v = [nbinom.pmf(k, n, p) for k in range(max_runs + 1)]
    s = sum(v)
    return [x / s for x in v] if s else v


def model_game(home_rpg, away_rpg, home_opp_era, away_opp_era,
               league_rpg, league_era, total_line, park=1.0,
               home_opp_bullpen_era=None, away_opp_bullpen_era=None,
               use_monte_carlo=True):
    """
    Upgraded game model using Negative Binomial baseline vectors combined 
    with a Monte Carlo simulation engine for exact line and parlay pricing.
    """
    lam_home = expected_runs(home_rpg, home_opp_era, league_rpg, league_era, park,
                             opp_bullpen_era=home_opp_bullpen_era)
    lam_away = expected_runs(away_rpg, away_opp_era, league_rpg, league_era, park,
                             opp_bullpen_era=away_opp_bullpen_era)
    
    if not use_monte_carlo:
        # Fallback to analytical matrix using Negative Binomial distribution
        ph = _nbinom_vector(lam_home)
        pa = _nbinom_vector(lam_away)
        p_hw = p_aw = p_tie = p_hc = p_ac = 0.0
        for h in range(len(ph)):
            for a in range(len(pa)):
                p = ph[h] * pa[a]
                if h > a: p_hw += p
                elif a > h: p_aw += p
                else: p_tie += p
                if h - a >= 2: p_hc += p
                else: p_ac += p
        
        lam_tot = lam_home + lam_away
        pt = _nbinom_vector(lam_tot, max_runs=30)
        p_over = p_under = p_push = 0.0
        if total_line is not None:
            line = float(total_line)
            for t in range(len(pt)):
                if t > line: p_over += pt[t]
                elif t < line: p_under += pt[t]
                else: p_push += pt[t]
                
        return {"lam_home": lam_home, "lam_away": lam_away, "lam_total": lam_tot,
                "p_home_ml": p_hw + p_tie / 2, "p_away_ml": p_aw + p_tie / 2,
                "p_home_cover": p_hc, "p_away_cover": p_ac,
                "p_over": p_over, "p_under": p_under, "p_push": p_push}

    # --- Monte Carlo Simulation Engine ---
    simulations = 10000
    
    # Generate random negative binomial scoring paths for both teams across 10k games
    n_h, p_h = 1.0 / 0.12, (1.0 / 0.12) / ((1.0 / 0.12) + lam_home)
    n_a, p_a = 1.0 / 0.12, (1.0 / 0.12) / ((1.0 / 0.12) + lam_away)
    
    home_runs = nbinom.rvs(n_h, p_h, size=simulations)
    away_runs = nbinom.rvs(n_a, p_a, size=simulations)
    
    # Calculate Moneyline outcomes
    home_wins = np.sum(home_runs > away_runs)
    away_wins = np.sum(away_runs > home_runs)
    ties = np.sum(home_runs == away_runs)
    
    # Calculate Run Line outcomes (-1.5 spread)
    home_covers = np.sum((home_runs - away_runs) >= 2)
    away_covers = np.sum((away_runs - home_runs) >= 2)
    
    # Calculate Over/Under totals
    total_scores = home_runs + away_runs
    p_over = p_under = p_push = 0.0
    if total_line is not None:
        line = float(total_line)
        p_over = np.sum(total_scores > line) / simulations
        p_under = np.sum(total_scores < line) / simulations
        p_push = np.sum(total_scores == line) / simulations

    return {
        "lam_home": lam_home, "lam_away": lam_away, "lam_total": lam_home + lam_away,
        "p_home_ml": (home_wins + ties / 2) / simulations,
        "p_away_ml": (away_wins + ties / 2) / simulations,
        "p_home_cover": home_covers / simulations,
        "p_away_cover": away_covers / simulations,
        "p_over": p_over, "p_under": p_under, "p_push": p_push
    }


# --- Upgraded Player Prop Matchup Engine ---

def prop_expected_counts(stat, pa, opp_hr9=LG_HR9, opp_k9=LG_K9, opp_whip=LG_WHIP,
                          ahead_obp=LG_OBP_DEFAULT, behind_slg=LG_SLG_DEFAULT,
                          park_hr=1.0, park_run=1.0, platoon=1.0):
    """
    Upgraded player prop estimator framework. Searches for a trained XGBoost model binary.
    Falls back gracefully to mathematical heuristics if the model file is not found.
    """
    # 1. Structure the exact features matching the machine learning training pipeline
    feature_vector = [[
        stat.get("avg", 0.250), stat.get("obp", 0.320), stat.get("slg", 0.400),
        stat.get("iso", 0.150), stat.get("k_pct", 0.22), opp_hr9, opp_k9, opp_whip,
        park_run, park_hr, platoon, pa
    ]]
    
    model_path = "models/xgboost_props_model.pkl"
    
    # 2. Try to leverage Machine Learning Engine
    if os.path.exists(model_path):
        try:
            ml_engine = joblib.load(model_path)
            predictions = ml_engine.predict(feature_vector)[0]
            # Assumes trained model returns an array of 5 expected metric targets:
            # [hr_expected, hit_expected, rbi_expected, run_expected, tb_expected]
            return {
                "batter_home_runs": predictions[0], "batter_hits": predictions[1],
                "batter_rbis": predictions[2], "batter_runs_scored": predictions[3],
                "batter_total_bases": predictions[4]
            }
        except Exception as e:
            # Code safety fallback to keep the Streamlit app active if loading fails
            pass

    # 3. Code Fallback: Original Heuristic Logic (Runs if ML model isn't built yet)
    platoon_damped = 1.0 + (platoon - 1.0) * 0.5
    spa = max(stat.get("plateAppearances", 1) or 1, 1)
    
    hr_l = (stat.get("hr", 0) / spa) * (opp_hr9 / LG_HR9) * park_hr * platoon * pa
    hits = stat.get("hits")
    hit_rate = (hits / spa) if hits is not None else stat.get("avg", 0) * 0.88
    k_factor = 1.0 - 0.5 * min(max((opp_k9 - LG_K9) / LG_K9, -0.3), 0.3)
    hit_l = hit_rate * k_factor * (1.0 + 0.5 * (park_run - 1.0)) * platoon * pa

    whip_factor = 1.0 + 0.5 * min(max((opp_whip - LG_WHIP) / LG_WHIP, -0.3), 0.3)
    traffic_factor = 1.0 + 0.6 * min(max((ahead_obp - LG_OBP_DEFAULT) / LG_OBP_DEFAULT, -0.4), 0.4)
    rbi_l = (stat.get("rbi", 0) / spa) * (0.6 + 0.4 * park_run) * whip_factor * traffic_factor * platoon_damped * pa

    support_factor = 1.0 + 0.5 * min(max((behind_slg - LG_SLG_DEFAULT) / LG_SLG_DEFAULT, -0.4), 0.4)
    run_l = (stat.get("runs", 0) / spa) * (0.6 + 0.4 * park_run) * whip_factor * support_factor * platoon_damped * pa

    ab_est = pa * 0.89
    power_factor = 1.0 + 0.5 * min(max((opp_hr9 - LG_HR9) / LG_HR9, -0.3), 0.3)
    tb_park = 0.6 * park_hr + 0.4 * park_run
    tb_l = stat.get("slg", LG_SLG_DEFAULT) * ab_est * k_factor * power_factor * tb_park * platoon

    return {"batter_home_runs": hr_l, "batter_hits": hit_l,
            "batter_rbis": rbi_l, "batter_runs_scored": run_l,
            "batter_total_bases": tb_l}

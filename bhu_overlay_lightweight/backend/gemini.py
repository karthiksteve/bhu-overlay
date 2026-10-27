"""
gemini.py - AI Recommendation & Legal Evaluation Layer
Provides optional, explainable AI consultation for Kurra land subdivision.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Gemini is an ADVISORY LAYER ONLY.
2. Gemini NEVER receives or generates polygon coordinates.
3. Gemini NEVER calculates or overrides mathematical areas.
4. Input to Gemini is strictly compact, summarized numerical/legal metadata.
5. Strict JSON response schema:
   {
       "recommended_strategy_index": int,
       "explanation": str,
       "warnings": list[str]
   }
6. If Gemini fails, is disabled, or times out, the system seamlessly falls back
   to the deterministic algorithmic choice.
"""

import os
import re
import json
import hashlib
import requests

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# In-memory recommendation cache: hash -> result dict
_GEMINI_CACHE = {}
_MAX_CACHE_SIZE = 64


def get_api_key():
    """Retrieve Gemini API key from environment."""
    return os.environ.get("GEMINI_API_KEY", "").strip()


def get_model():
    """Retrieve Gemini model name."""
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()


def build_compact_payload(parcel_metrics, strategies, road_info=None, river_info=None, user_preferences=""):
    """
    Build a small numerical-only summary for Gemini.
    No raw polygon coordinates are included.
    """
    compact_strategies = []
    for idx, s in enumerate(strategies):
        sub_stats = s.get("sub_plot_stats", [])
        compact_strategies.append({
            "index": idx,
            "name": s["name"],
            "areas": [round(p.area, 1) for p in s["polys"]],
            "frontages": [round(st.get("frontage_m", 0), 1) for st in sub_stats] if sub_stats else [],
            "features_contained": [st.get("features", 0) for st in sub_stats] if sub_stats else []
        })

    if not user_preferences and compact_strategies and compact_strategies[0]["areas"]:
        areas = compact_strategies[0]["areas"]
        total_a = sum(areas)
        if total_a > 0:
            pcts = [round(a / total_a * 100.0, 1) for a in areas]
            is_equal = all(abs(p - pcts[0]) < 1.0 for p in pcts)
            if is_equal:
                user_preferences = f"Equal partition among {len(areas)} co-sharers"
            else:
                user_preferences = f"Partition according to requested co-sharer shares: {', '.join(str(p) + '%' for p in pcts)}"

    return {
        "parcel_area_sqm": parcel_metrics.get("area_sqm", 0),
        "road_access": bool(road_info and road_info.get("name")),
        "road_name": road_info.get("name", "None") if road_info else "None",
        "river_access": bool(river_info and river_info.get("name")),
        "river_name": river_info.get("name", "None") if river_info else "None",
        "user_preferences": user_preferences or "Equitable partition respecting Rule 109",
        "strategies": compact_strategies
    }


def evaluate_strategies(parcel_metrics, strategies, road_info=None, river_info=None, user_preferences="", timeout_sec=12):
    """
    Consult Gemini to evaluate and rank deterministic land subdivision strategies.
    Returns:
    {
        "recommended_strategy_index": int,
        "explanation": str,
        "warnings": list[str],
        "success": bool
    }
    """
    if not strategies:
        return {
            "recommended_strategy_index": 0,
            "explanation": "No subdivision strategies provided.",
            "warnings": ["Empty strategy list"],
            "success": False
        }

    # Deterministic fallback response if AI is unavailable or fails
    fallback_response = {
        "recommended_strategy_index": 0,
        "explanation": (
            f"Deterministic geometry-based recommendation (AI advisory offline or skipped). "
            f"Selected '{strategies[0]['name']}' which maximizes geometric compactness and boundary regularity."
        ),
        "warnings": [],
        "success": True,
        "fallback": True
    }

    api_key = get_api_key()
    if not api_key:
        return fallback_response

    payload = build_compact_payload(parcel_metrics, strategies, road_info, river_info, user_preferences)

    # Check in-memory cache
    cache_key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    if cache_key in _GEMINI_CACHE:
        return _GEMINI_CACHE[cache_key]

    system_prompt = (
        "You are an expert revenue surveyor and cadastral lawyer evaluating land subdivision (Kurra) "
        "under the Uttar Pradesh / Bihar Revenue Code (Rules 109(b), 109(f), 109(g)).\n"
        "Guidelines:\n"
        "- Rule 109(b): Compactness — avoid narrow, elongated, or unusable strips.\n"
        "- Rule 109(f): Proportional road or commercial frontage access to all co-sharers.\n"
        "- Rule 109(g): Mutual consent / user preferences take priority.\n"
        "You MUST respond ONLY with valid JSON strictly adhering to this schema:\n"
        "{\n"
        '  "recommended_strategy_index": <int>,\n'
        '  "explanation": "<2-3 sentence legal and technical justification>",\n'
        '  "warnings": ["<optional warning>"]\n'
        "}\n"
        "Do not output markdown backticks, explanations outside JSON, or coordinates."
    )

    user_prompt = f"Evaluate these deterministic subdivision options and return JSON:\n{json.dumps(payload, indent=2)}"

    try:
        model = get_model()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
                "response_mime_type": "application/json"
            }
        }

        resp = requests.post(url, json=body, timeout=timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Clean markdown codeblocks if returned
        clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.MULTILINE).strip()
        parsed = json.loads(clean_json)

        rec_idx = int(parsed.get("recommended_strategy_index", 0))
        if rec_idx < 0 or rec_idx >= len(strategies):
            rec_idx = 0

        result = {
            "recommended_strategy_index": rec_idx,
            "explanation": str(parsed.get("explanation", "")).strip(),
            "warnings": parsed.get("warnings", []),
            "success": True,
            "fallback": False
        }

        if len(_GEMINI_CACHE) < _MAX_CACHE_SIZE:
            _GEMINI_CACHE[cache_key] = result
        return result

    except Exception as e:
        print(f"[gemini.py] Gemini API call skipped or failed ({e}). Using deterministic fallback.")
        return fallback_response

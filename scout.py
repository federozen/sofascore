"""
scout.py  –  Scout: Chat deportivo con SofaScore
Ejecutar:  streamlit run scout.py
"""

import streamlit as st
import json, re
from curl_cffi import requests as c_requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import anthropic

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Scout · Fútbol en vivo",
    page_icon="🔬",
    layout="centered",
)

TZ_BA  = ZoneInfo("America/Argentina/Buenos_Aires")
NOW_BA = datetime.now(TZ_BA)
TODAY  = NOW_BA.date()
TODAY_ISO = TODAY.isoformat()

# ─────────────────────────────────────────────────────────────
# CSS  —  aesthetic: editorial/minimalista con acento rojo
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

.scout-logo {
    font-family: 'DM Serif Display', serif;
    font-size: 2.1rem;
    color: #c0392b;
    letter-spacing: -1px;
    line-height: 1;
}
.scout-sub {
    font-size: .78rem;
    color: #888;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-top: .1rem;
}

/* cards de resultado */
.card {
    border: 1px solid rgba(0,0,0,.08);
    border-radius: 10px;
    padding: .9rem 1.1rem;
    margin: .4rem 0;
    background: rgba(255,255,255,.03);
    font-size: .88rem;
    line-height: 1.7;
}
.card-red   { border-left: 4px solid #c0392b; }
.card-green { border-left: 4px solid #27ae60; }
.card-blue  { border-left: 4px solid #2980b9; }
.card-gray  { border-left: 4px solid #95a5a6; }

/* pills */
.pill {
    display: inline-block;
    padding: .12rem .55rem;
    border-radius: 20px;
    font-size: .7rem;
    font-weight: 600;
    letter-spacing: .03em;
    margin: .1rem .15rem;
}
.pill-red   { background:#fdecea; color:#c0392b; }
.pill-green { background:#eafaf1; color:#1e8449; }
.pill-blue  { background:#eaf4fb; color:#1a6fa0; }
.pill-gray  { background:#f2f3f4; color:#566573; }

.divider-line {
    border: none;
    border-top: 1px solid rgba(128,128,128,.15);
    margin: .6rem 0;
}

.example-btn { font-size:.82rem !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# API KEY  —  secrets primero, fallback a text_input
# ─────────────────────────────────────────────────────────────
_secret_key = ""
try:
    _secret_key = st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:
    pass


# ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════
#  SOFASCORE — capa de datos
# ══════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────

HEADERS = {
    "Accept-Language": "es-AR,es;q=0.9",
    "Origin":  "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
}

def _get(url: str, timeout: int = 15) -> dict | None:
    try:
        r = c_requests.get(url, impersonate="chrome120", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ── Búsqueda general ─────────────────────────────────────────

def search_entity(query: str) -> dict:
    """Busca equipos, jugadores y torneos por nombre."""
    data = _get(f"https://api.sofascore.com/api/v1/search/multi-suggest?q={query}")
    if not data:
        return {"teams": [], "players": [], "tournaments": []}

    teams, players, tournaments = [], [], []

    for item in data.get("teams", {}).get("hits", [])[:5]:
        t = item.get("entity", {})
        sport = t.get("sport", {}).get("slug", "")
        if sport != "football":
            continue
        teams.append({
            "id":      t.get("id"),
            "name":    t.get("name", ""),
            "country": t.get("country", {}).get("name", ""),
            "sport":   sport,
        })

    for item in data.get("players", {}).get("hits", [])[:5]:
        p = item.get("entity", {})
        teams_p = p.get("team", {})
        players.append({
            "id":       p.get("id"),
            "name":     p.get("name", ""),
            "position": p.get("position", ""),
            "team":     teams_p.get("name", "") if teams_p else "",
            "country":  p.get("country", {}).get("name", ""),
        })

    for item in data.get("tournaments", {}).get("hits", [])[:5]:
        t = item.get("entity", {})
        sport = t.get("sport", {}).get("slug", "")
        if sport != "football":
            continue
        tournaments.append({
            "id":      t.get("id"),
            "name":    t.get("name", ""),
            "country": t.get("category", {}).get("name", ""),
        })

    return {"teams": teams, "players": players, "tournaments": tournaments}


# ── Próximos partidos ─────────────────────────────────────────

def _parse_event(ev: dict) -> dict:
    ts = ev.get("startTimestamp")
    if not ts:
        return {}
    dt = datetime.fromtimestamp(ts, ZoneInfo("UTC")).astimezone(TZ_BA)
    return {
        "id":          ev.get("id"),
        "date":        dt.date().isoformat(),
        "time":        dt.strftime("%H:%M"),
        "home":        ev.get("homeTeam", {}).get("name", ""),
        "away":        ev.get("awayTeam", {}).get("name", ""),
        "name":        f"{ev.get('homeTeam',{}).get('name','')} vs {ev.get('awayTeam',{}).get('name','')}",
        "competition": ev.get("tournament", {}).get("name", ""),
        "category":    ev.get("tournament", {}).get("category", {}).get("name", ""),
        "status_type": ev.get("status", {}).get("type", ""),
        "status_desc": ev.get("status", {}).get("description", ""),
        "score_home":  ev.get("homeScore", {}).get("current"),
        "score_away":  ev.get("awayScore", {}).get("current"),
        "round":       ev.get("roundInfo", {}).get("round"),
    }

def team_next_matches(team_id: int, n: int = 10) -> list[dict]:
    events = []
    for page in range(0, 3):
        data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/{page}")
        if not data:
            break
        batch = data.get("events", [])
        if not batch:
            break
        for ev in batch:
            parsed = _parse_event(ev)
            if parsed and parsed["date"] >= TODAY_ISO:
                events.append(parsed)
        if len(events) >= n:
            break
    return events[:n]

def tournament_next_matches(tournament_id: int, n: int = 20) -> list[dict]:
    # obtener season activa
    data_s = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/seasons")
    if not data_s:
        return []
    seasons = data_s.get("seasons", [])
    if not seasons:
        return []
    season_id = seasons[0]["id"]

    events = []
    for page in range(0, 4):
        data = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/season/{season_id}/events/next/{page}")
        if not data:
            break
        batch = data.get("events", [])
        if not batch:
            break
        for ev in batch:
            parsed = _parse_event(ev)
            if parsed and parsed["date"] >= TODAY_ISO:
                events.append(parsed)
        if len(events) >= n:
            break
    return events[:n]


# ── Resultados recientes ──────────────────────────────────────

def team_last_matches(team_id: int, n: int = 10) -> list[dict]:
    events = []
    for page in range(0, 3):
        data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/{page}")
        if not data:
            break
        batch = data.get("events", [])
        if not batch:
            break
        for ev in reversed(batch):
            parsed = _parse_event(ev)
            if parsed:
                events.append(parsed)
        if len(events) >= n:
            break
    return events[:n]

def tournament_last_matches(tournament_id: int, n: int = 20) -> list[dict]:
    data_s = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/seasons")
    if not data_s:
        return []
    seasons = data_s.get("seasons", [])
    if not seasons:
        return []
    season_id = seasons[0]["id"]

    events = []
    for page in range(0, 3):
        data = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/season/{season_id}/events/last/{page}")
        if not data:
            break
        batch = data.get("events", [])
        if not batch:
            break
        for ev in reversed(batch):
            parsed = _parse_event(ev)
            if parsed:
                events.append(parsed)
        if len(events) >= n:
            break
    return events[:n]


# ── Tabla de posiciones ───────────────────────────────────────

def get_standings(tournament_id: int) -> list[dict]:
    data_s = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/seasons")
    if not data_s:
        return []
    seasons = data_s.get("seasons", [])
    if not seasons:
        return []
    season_id = seasons[0]["id"]

    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/season/{season_id}/standings/total")
    if not data:
        return []

    rows = []
    for group in data.get("standings", []):
        for row in group.get("rows", []):
            team = row.get("team", {})
            rows.append({
                "pos":   row.get("position"),
                "team":  team.get("name", ""),
                "pj":    row.get("matches", 0),
                "g":     row.get("wins", 0),
                "e":     row.get("draws", 0),
                "p":     row.get("losses", 0),
                "gf":    row.get("scoresFor", 0),
                "gc":    row.get("scoresAgainst", 0),
                "dif":   row.get("scoresFor", 0) - row.get("scoresAgainst", 0),
                "pts":   row.get("points", 0),
                "forma": row.get("promotion", {}).get("text", ""),
            })
    return sorted(rows, key=lambda x: x["pos"] or 99)


# ── Estadísticas de jugador ───────────────────────────────────

def player_stats(player_id: int) -> dict:
    # Info básica
    info_data = _get(f"https://api.sofascore.com/api/v1/player/{player_id}")
    player_info = {}
    if info_data:
        p = info_data.get("player", {})
        player_info = {
            "name":         p.get("name", ""),
            "position":     p.get("position", ""),
            "nationality":  p.get("country", {}).get("name", ""),
            "age":          p.get("age"),
            "height":       p.get("height"),
            "preferred_foot": p.get("preferredFoot", ""),
            "market_value": p.get("proposedMarketValue"),
            "team":         p.get("team", {}).get("name", "") if p.get("team") else "",
        }

    # Stats de temporada — buscamos en el team actual
    stats_data = _get(f"https://api.sofascore.com/api/v1/player/{player_id}/statistics/seasons")
    stats = {}
    if stats_data:
        seasons_list = stats_data.get("seasons", [])
        if seasons_list:
            latest = seasons_list[0]
            tid = latest.get("tournament", {}).get("id")
            sid = latest.get("year")
            if tid:
                sd = _get(f"https://api.sofascore.com/api/v1/player/{player_id}/tournament/{tid}/season/{sid}/statistics/overall")
                if sd:
                    s = sd.get("statistics", {})
                    stats = {
                        "goles":       s.get("goals", 0),
                        "asistencias": s.get("goalAssist", 0),
                        "partidos":    s.get("appearances", 0),
                        "minutos":     s.get("minutesPlayed", 0),
                        "amarillas":   s.get("yellowCards", 0),
                        "rojas":       s.get("redCards", 0),
                        "rating":      round(s.get("rating", 0), 2),
                        "competencia": latest.get("tournament", {}).get("name", ""),
                    }

    return {"info": player_info, "stats": stats}


# ── Info de equipo ────────────────────────────────────────────

def team_info(team_id: int) -> dict:
    data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}")
    if not data:
        return {}
    t = data.get("team", {})
    return {
        "name":     t.get("name", ""),
        "country":  t.get("country", {}).get("name", ""),
        "founded":  t.get("foundationDateTimestamp"),
        "venue":    t.get("venue", {}).get("name", "") if t.get("venue") else "",
        "manager":  t.get("manager", {}).get("name", "") if t.get("manager") else "",
        "national": t.get("national", False),
    }

def team_players(team_id: int) -> list[dict]:
    data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/players")
    if not data:
        return []
    players = []
    for item in data.get("players", []):
        p = item.get("player", {})
        players.append({
            "name":     p.get("name", ""),
            "position": p.get("position", ""),
            "age":      p.get("age"),
            "country":  p.get("country", {}).get("name", ""),
            "shirt":    p.get("jerseyNumber"),
            "value":    p.get("proposedMarketValue"),
        })
    return players

def team_season_stats(team_id: int) -> dict:
    """Stats globales del equipo en la temporada actual."""
    # Buscar temporada activa en sus torneos recientes
    data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/tournaments")
    stats_out = {}
    if not data:
        return stats_out
    tournaments = data.get("tournaments", [])[:2]
    for t in tournaments:
        tid = t.get("id")
        data_s = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/seasons")
        if not data_s or not data_s.get("seasons"):
            continue
        sid = data_s["seasons"][0]["id"]
        sd = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/tournament/{tid}/season/{sid}/statistics/overall")
        if sd:
            s = sd.get("statistics", {})
            stats_out[t.get("name", "Torneo")] = {
                "pj":            s.get("matches", 0),
                "victorias":     s.get("wins", 0),
                "empates":       s.get("draws", 0),
                "derrotas":      s.get("losses", 0),
                "goles_favor":   s.get("goalsScored", 0),
                "goles_contra":  s.get("goalsConceded", 0),
                "rating_prom":   round(s.get("rating", 0), 2),
                "posesion_prom": round(s.get("possessionPercentage", 0), 1),
            }
    return stats_out


# ── Goleadores de torneo ──────────────────────────────────────

def tournament_top_scorers(tournament_id: int, n: int = 10) -> list[dict]:
    data_s = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/seasons")
    if not data_s or not data_s.get("seasons"):
        return []
    season_id = data_s["seasons"][0]["id"]

    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/season/{season_id}/top-players/goals")
    if not data:
        return []

    result = []
    for item in data.get("topPlayers", [])[:n]:
        p = item.get("player", {})
        t = item.get("team", {})
        result.append({
            "nombre": p.get("name", ""),
            "equipo": t.get("name", ""),
            "pais":   p.get("country", {}).get("name", ""),
            "goles":  item.get("statistics", {}).get("goals", 0),
        })
    return result

def tournament_top_assists(tournament_id: int, n: int = 10) -> list[dict]:
    data_s = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/seasons")
    if not data_s or not data_s.get("seasons"):
        return []
    season_id = data_s["seasons"][0]["id"]

    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tournament_id}/season/{season_id}/top-players/assists")
    if not data:
        return []

    result = []
    for item in data.get("topPlayers", [])[:n]:
        p = item.get("player", {})
        t = item.get("team", {})
        result.append({
            "nombre":      p.get("name", ""),
            "equipo":      t.get("name", ""),
            "asistencias": item.get("statistics", {}).get("goalAssist", 0),
        })
    return result


# ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════
#  CLAUDE — inteligencia
# ══════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────

INTENT_SYSTEM = f"""Sos un asistente que interpreta preguntas sobre fútbol y decide qué datos buscar.
Hoy es {TODAY.strftime('%A %d de %B de %Y')} (Buenos Aires, Argentina).

Devolvé SOLO un JSON con esta estructura (sin markdown):
{{
  "intent": uno de: "team_next" | "team_last" | "team_info" | "team_players" | "team_stats" |
                    "tournament_next" | "tournament_last" | "tournament_standings" |
                    "tournament_scorers" | "tournament_assists" |
                    "player_stats" | "multi",
  "query_team": "nombre del equipo si aplica, sino null",
  "query_tournament": "nombre del torneo/liga si aplica, sino null",
  "query_player": "nombre del jugador si aplica, sino null",
  "n": número de resultados a traer (default 10),
  "extra": "info adicional útil"
}}

REGLAS:
- "¿Cuándo juega X?" → team_next
- "Últimos partidos / resultados de X" → team_last
- "Info / datos de X (equipo)" → team_info + team_players (usar multi)
- "Plantel / jugadores de X" → team_players
- "Stats / estadísticas de X (equipo)" → team_stats
- "Próximos partidos de [liga]" → tournament_next
- "Resultados de [liga]" → tournament_last
- "Tabla / posiciones de [liga]" → tournament_standings
- "Goleadores de [liga]" → tournament_scorers
- "Asistencias / asistidores de [liga]" → tournament_assists
- "Stats / info de [jugador]" → player_stats
- Preguntas combinadas → multi (podés devolver una lista de intents en "intent")
"""

RESPONSE_SYSTEM = f"""Sos Scout, un asistente de fútbol experto, conciso y apasionado.
Hoy es {TODAY.strftime('%A %d de %B de %Y')} (hora Buenos Aires).

Recibís datos de SofaScore y respondés en español rioplatense de manera clara, bien organizada y útil.
Usá formato markdown cuando ayude (negrita, listas). Sé concreto.
Para fechas usá formato amigable: "hoy", "mañana", "sábado 5/4", etc.
Horarios siempre en hora Argentina (ya vienen convertidos).
Si los datos están vacíos o faltan, decilo honestamente y sugerí qué consultar.
No seas genérico: destacá lo interesante de los datos.
"""

def parse_intent(user_msg: str, cliente: anthropic.Anthropic) -> dict:
    try:
        r = cliente.messages.create(
            model="claude-opus-4-5", max_tokens=400,
            system=INTENT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = r.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"```$", "", raw).strip()
        return json.loads(raw)
    except Exception:
        return {"intent": "team_next", "query_team": user_msg, "query_tournament": None, "query_player": None, "n": 10}


def fetch_all_data(intent_data: dict) -> dict:
    """Orquesta todas las llamadas a SofaScore según la intención."""
    intent  = intent_data.get("intent", "team_next")
    intents = [intent] if isinstance(intent, str) else intent

    qt  = intent_data.get("query_team")
    qtour = intent_data.get("query_tournament")
    qp  = intent_data.get("query_player")
    n   = int(intent_data.get("n", 10))

    result = {}
    search_info = []

    # Resolver entidades
    team_id, tourn_id, player_id = None, None, None

    if qt:
        ents = search_entity(qt)
        if ents["teams"]:
            best_team = ents["teams"][0]
            team_id = best_team["id"]
            search_info.append(f"🔵 Equipo: **{best_team['name']}** ({best_team['country']})")
        # a veces el query es un torneo escrito como equipo
        if not team_id and ents["tournaments"]:
            best_tourn = ents["tournaments"][0]
            tourn_id = best_tourn["id"]
            search_info.append(f"🏆 Competencia: **{best_tourn['name']}** ({best_tourn['country']})")

    if qtour and not tourn_id:
        ents = search_entity(qtour)
        if ents["tournaments"]:
            best_tourn = ents["tournaments"][0]
            tourn_id = best_tourn["id"]
            search_info.append(f"🏆 Competencia: **{best_tourn['name']}** ({best_tourn['country']})")
        elif ents["teams"]:
            best_team = ents["teams"][0]
            team_id = best_team["id"]
            search_info.append(f"🔵 Equipo: **{best_team['name']}** ({best_team['country']})")

    if qp:
        ents = search_entity(qp)
        if ents["players"]:
            best_player = ents["players"][0]
            player_id = best_player["id"]
            search_info.append(f"👤 Jugador: **{best_player['name']}** ({best_player.get('team','')}, {best_player['country']})")

    result["_search_info"] = search_info

    # Ejecutar cada intent
    for it in intents:
        if it == "team_next" and team_id:
            result["proximos_partidos"] = team_next_matches(team_id, n)

        elif it == "team_last" and team_id:
            result["resultados_recientes"] = team_last_matches(team_id, n)

        elif it == "team_info" and team_id:
            result["info_equipo"] = team_info(team_id)

        elif it == "team_players" and team_id:
            result["plantel"] = team_players(team_id)

        elif it == "team_stats" and team_id:
            result["estadisticas_equipo"] = team_season_stats(team_id)

        elif it == "tournament_next" and tourn_id:
            result["proximos_partidos"] = tournament_next_matches(tourn_id, n)

        elif it == "tournament_last" and tourn_id:
            result["resultados_recientes"] = tournament_last_matches(tourn_id, n)

        elif it == "tournament_standings" and tourn_id:
            result["tabla_posiciones"] = get_standings(tourn_id)

        elif it == "tournament_scorers" and tourn_id:
            result["goleadores"] = tournament_top_scorers(tourn_id, n)

        elif it == "tournament_assists" and tourn_id:
            result["asistidores"] = tournament_top_assists(tourn_id, n)

        elif it == "player_stats" and player_id:
            result["jugador"] = player_stats(player_id)

    return result


def generate_response(user_msg: str, data: dict, history: list, cliente: anthropic.Anthropic) -> str:
    # Limpiar metadatos internos del JSON que va a Claude
    data_clean = {k: v for k, v in data.items() if not k.startswith("_")}
    data_str = json.dumps(data_clean, ensure_ascii=False, indent=2)

    # Limitar tamaño para no saturar contexto
    if len(data_str) > 12000:
        data_str = data_str[:12000] + "\n... [datos truncados]"

    messages = history + [{
        "role": "user",
        "content": f"Pregunta: {user_msg}\n\nDatos de SofaScore:\n{data_str}"
    }]

    try:
        r = cliente.messages.create(
            model="claude-opus-4-5", max_tokens=1500,
            system=RESPONSE_SYSTEM,
            messages=messages,
        )
        return r.content[0].text.strip()
    except Exception as e:
        return f"Error al generar respuesta: {e}"


# ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────

# Header
col_logo, col_date = st.columns([3, 1])
with col_logo:
    st.markdown('<div class="scout-logo">🔬 Scout</div>', unsafe_allow_html=True)
    st.markdown('<div class="scout-sub">Fútbol · SofaScore en tiempo real</div>', unsafe_allow_html=True)
with col_date:
    st.markdown(f"<div style='text-align:right;font-size:.78rem;color:#888;padding-top:.5rem'>{TODAY.strftime('%d/%m/%Y')}<br>Buenos Aires</div>", unsafe_allow_html=True)

st.markdown("<hr style='border:none;border-top:2px solid #c0392b;margin:.4rem 0 1rem 0'>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuración")

    if _secret_key:
        api_key = _secret_key
        st.success("🔑 API Key cargada", icon="✅")
    else:
        raw_key = st.text_input("🔑 Anthropic API Key", type="password", placeholder="sk-ant-api03-...")
        api_key = raw_key.strip() if raw_key else ""
        if api_key:
            st.success("✅ Key cargada") if api_key.startswith("sk-ant-") else st.error("⚠️ Formato incorrecto")

    st.divider()
    st.markdown("### 💡 Ejemplos")

    grupos = {
        "⚽ Equipos": [
            "¿Cuándo juega River?",
            "Últimos resultados de Boca",
            "Plantel de Vélez",
            "Estadísticas de Racing esta temporada",
        ],
        "🏆 Ligas": [
            "Tabla de la Liga Profesional",
            "Próximos partidos de la Champions",
            "Resultados de la Premier League",
            "Goleadores de la Libertadores",
        ],
        "👤 Jugadores": [
            "Estadísticas de Messi",
            "¿Cómo viene Mbappé esta temporada?",
            "Info sobre Lautaro Martínez",
        ],
    }

    for grupo, ejemplos in grupos.items():
        st.markdown(f"**{grupo}**")
        for e in ejemplos:
            if st.button(e, key=f"ej_{e}", use_container_width=True):
                st.session_state["preset_msg"] = e

    st.divider()
    if st.button("🗑️ Nueva conversación", use_container_width=True):
        st.session_state["messages"] = []
        st.session_state["claude_history"] = []
        st.rerun()

# Estado
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "claude_history" not in st.session_state:
    st.session_state["claude_history"] = []

# Historial de chat
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
preset = st.session_state.pop("preset_msg", None)
user_input = st.chat_input("Preguntá sobre partidos, resultados, tablas, jugadores...")
if preset:
    user_input = preset

if user_input:
    if not api_key or not api_key.startswith("sk-ant-"):
        st.error("⚠️ Ingresá tu API Key de Anthropic en el panel lateral.")
        st.stop()

    # Mostrar mensaje usuario
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Respuesta
    with st.chat_message("assistant"):
        with st.spinner("🔎 Consultando SofaScore..."):
            cliente = anthropic.Anthropic(api_key=api_key)

            # 1. Parsear intención
            intent_data = parse_intent(user_input, cliente)

            # 2. Traer datos
            data = fetch_all_data(intent_data)

            # Mostrar qué se encontró
            for info in data.get("_search_info", []):
                st.caption(info)

            # 3. Generar respuesta con historial
            response = generate_response(
                user_input, data,
                st.session_state["claude_history"],
                cliente
            )

        st.markdown(response)

    # Guardar en historial
    st.session_state["messages"].append({"role": "assistant", "content": response})
    # Historial para Claude (sin los datos crudos, solo el diálogo)
    st.session_state["claude_history"].append({"role": "user", "content": user_input})
    st.session_state["claude_history"].append({"role": "assistant", "content": response})
    # Mantener últimos 10 turnos para no saturar
    if len(st.session_state["claude_history"]) > 20:
        st.session_state["claude_history"] = st.session_state["claude_history"][-20:]

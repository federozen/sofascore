"""
scout.py  –  Scout: Chat deportivo con SofaScore  (v2)
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
    page_title="Scout · Fútbol",
    page_icon="🔬",
    layout="centered",
)

TZ_BA     = ZoneInfo("America/Argentina/Buenos_Aires")
TODAY     = datetime.now(TZ_BA).date()
TODAY_ISO = TODAY.isoformat()

# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.scout-logo {
    font-family: 'DM Serif Display', serif;
    font-size: 2rem; color: #c0392b;
    letter-spacing: -1px; line-height: 1;
}
.scout-sub {
    font-size: .75rem; color: #999;
    letter-spacing: .08em; text-transform: uppercase; margin-top:.1rem;
}
.debug-box {
    background: rgba(0,0,0,.04);
    border: 1px solid rgba(0,0,0,.1);
    border-radius: 6px;
    padding: .4rem .7rem;
    font-size: .72rem;
    font-family: monospace;
    color: #555;
    margin: .2rem 0;
    word-break: break-all;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────────────────────
_secret_key = ""
try:
    _secret_key = st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:
    pass

# ─────────────────────────────────────────────────────────────
# SOFASCORE — capa de datos
# ─────────────────────────────────────────────────────────────

HEADERS = {
    "Accept":          "application/json",
    "Accept-Language": "es-AR,es;q=0.9",
    "Origin":          "https://www.sofascore.com",
    "Referer":         "https://www.sofascore.com/",
    "User-Agent":      (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

_api_log: list[str] = []


def _get(url: str, timeout: int = 15) -> dict | None:
    _api_log.append(f"GET {url}")
    try:
        r = c_requests.get(url, impersonate="chrome120", headers=HEADERS, timeout=timeout)
        _api_log.append(f"  → {r.status_code}")
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        _api_log.append(f"  → ERROR: {e}")
        return None


# ── Búsqueda ─────────────────────────────────────────────────

def _search_raw(query: str) -> dict:
    """Intenta los dos endpoints de búsqueda de Sofa."""
    data = _get(f"https://api.sofascore.com/api/v1/search/multi-suggest?q={query}")
    if data:
        return data
    # fallback
    data2 = _get(f"https://api.sofascore.com/api/v1/search?q={query}&page=0")
    if data2:
        # normalizar al formato de multi-suggest
        hits_teams  = [{"entity": r["entity"]} for r in data2.get("results", []) if r.get("type") == "team"]
        hits_tourn  = [{"entity": r["entity"]} for r in data2.get("results", []) if r.get("type") == "tournament"]
        hits_player = [{"entity": r["entity"]} for r in data2.get("results", []) if r.get("type") == "player"]
        return {
            "teams":       {"hits": hits_teams},
            "tournaments": {"hits": hits_tourn},
            "players":     {"hits": hits_player},
        }
    return {}


def search_team(query: str) -> list[dict]:
    raw = _search_raw(query)
    out = []
    for item in raw.get("teams", {}).get("hits", [])[:6]:
        e = item.get("entity", {})
        sport = e.get("sport", {}).get("slug", "football")
        if sport != "football":
            continue
        out.append({
            "id":      e.get("id"),
            "name":    e.get("name", ""),
            "country": e.get("country", {}).get("name", ""),
        })
    return out


def search_tournament(query: str) -> list[dict]:
    raw = _search_raw(query)
    out = []
    for item in raw.get("tournaments", {}).get("hits", [])[:5]:
        e = item.get("entity", {})
        sport = e.get("sport", {}).get("slug", "football")
        if sport != "football":
            continue
        out.append({
            "id":      e.get("id"),
            "name":    e.get("name", ""),
            "country": e.get("category", {}).get("name", e.get("country", {}).get("name", "")),
        })
    return out


def search_player(query: str) -> list[dict]:
    raw = _search_raw(query)
    out = []
    for item in raw.get("players", {}).get("hits", [])[:5]:
        p = item.get("entity", {})
        sport = p.get("sport", {}).get("slug", "football")
        if sport != "football":
            continue
        team = p.get("team", {}) or {}
        out.append({
            "id":       p.get("id"),
            "name":     p.get("name", ""),
            "team":     team.get("name", ""),
            "country":  p.get("country", {}).get("name", ""),
            "position": p.get("position", ""),
        })
    return out


# ── Helpers ──────────────────────────────────────────────────

def _parse_event(ev: dict) -> dict | None:
    ts = ev.get("startTimestamp")
    if not ts:
        return None
    dt   = datetime.fromtimestamp(ts, ZoneInfo("UTC")).astimezone(TZ_BA)
    home = ev.get("homeTeam", {}).get("name", "")
    away = ev.get("awayTeam", {}).get("name", "")
    sh   = ev.get("homeScore", {}).get("current")
    sa   = ev.get("awayScore", {}).get("current")
    return {
        "id":          ev.get("id"),
        "date":        dt.date().isoformat(),
        "time":        dt.strftime("%H:%M"),
        "home":        home,
        "away":        away,
        "score":       f"{sh} - {sa}" if sh is not None and sa is not None else "-",
        "competition": ev.get("tournament", {}).get("name", ""),
        "category":    ev.get("tournament", {}).get("category", {}).get("name", ""),
        "status":      ev.get("status", {}).get("type", "notstarted"),
        "round":       ev.get("roundInfo", {}).get("round"),
    }


def get_season(tid: int) -> int | None:
    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/seasons")
    if data and data.get("seasons"):
        return data["seasons"][0]["id"]
    return None


# ── Próximos partidos ─────────────────────────────────────────

def team_next(team_id: int, n: int = 8) -> list[dict]:
    events = []
    for page in range(3):
        data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/{page}")
        if not data:
            break
        for ev in data.get("events", []):
            p = _parse_event(ev)
            if p and p["date"] >= TODAY_ISO:
                events.append(p)
        if len(events) >= n:
            break
    return sorted(events, key=lambda x: (x["date"], x["time"]))[:n]


def tournament_next(tid: int, sid: int, n: int = 15) -> list[dict]:
    events = []
    for page in range(4):
        data = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/season/{sid}/events/next/{page}")
        if not data:
            break
        batch = data.get("events", [])
        if not batch:
            break
        for ev in batch:
            p = _parse_event(ev)
            if p and p["date"] >= TODAY_ISO:
                events.append(p)
        if len(events) >= n:
            break
    return sorted(events, key=lambda x: (x["date"], x["time"]))[:n]


# ── Resultados recientes ──────────────────────────────────────

def team_last(team_id: int, n: int = 8) -> list[dict]:
    events = []
    for page in range(3):
        data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/{page}")
        if not data:
            break
        for ev in reversed(data.get("events", [])):
            p = _parse_event(ev)
            if p:
                events.append(p)
        if len(events) >= n:
            break
    return events[:n]


def tournament_last(tid: int, sid: int, n: int = 15) -> list[dict]:
    events = []
    for page in range(3):
        data = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/season/{sid}/events/last/{page}")
        if not data:
            break
        batch = data.get("events", [])
        if not batch:
            break
        for ev in reversed(batch):
            p = _parse_event(ev)
            if p:
                events.append(p)
        if len(events) >= n:
            break
    return events[:n]


# ── Tabla de posiciones ───────────────────────────────────────

def standings(tid: int, sid: int) -> list[dict]:
    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/season/{sid}/standings/total")
    if not data:
        return []
    rows = []
    for group in data.get("standings", []):
        for row in group.get("rows", []):
            rows.append({
                "pos":  row.get("position", 0),
                "team": row.get("team", {}).get("name", ""),
                "pj":   row.get("matches", 0),
                "g":    row.get("wins", 0),
                "e":    row.get("draws", 0),
                "p":    row.get("losses", 0),
                "gf":   row.get("scoresFor", 0),
                "gc":   row.get("scoresAgainst", 0),
                "dif":  row.get("scoresFor", 0) - row.get("scoresAgainst", 0),
                "pts":  row.get("points", 0),
            })
    return sorted(rows, key=lambda x: x["pos"])


# ── Goleadores / asistidores ──────────────────────────────────

def top_scorers(tid: int, sid: int, n: int = 10) -> list[dict]:
    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/season/{sid}/top-players/goals")
    if not data:
        return []
    out = []
    for item in data.get("topPlayers", [])[:n]:
        p = item.get("player", {})
        t = item.get("team", {})
        out.append({
            "nombre": p.get("name", ""),
            "equipo": t.get("name", ""),
            "goles":  item.get("statistics", {}).get("goals", 0),
        })
    return out


def top_assists(tid: int, sid: int, n: int = 10) -> list[dict]:
    data = _get(f"https://api.sofascore.com/api/v1/tournament/{tid}/season/{sid}/top-players/assists")
    if not data:
        return []
    out = []
    for item in data.get("topPlayers", [])[:n]:
        p = item.get("player", {})
        t = item.get("team", {})
        out.append({
            "nombre":      p.get("name", ""),
            "equipo":      t.get("name", ""),
            "asistencias": item.get("statistics", {}).get("goalAssist", 0),
        })
    return out


# ── Info equipo + plantel ─────────────────────────────────────

def team_info(team_id: int) -> dict:
    data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}")
    if not data:
        return {}
    t = data.get("team", {})
    return {
        "nombre":  t.get("name", ""),
        "pais":    t.get("country", {}).get("name", ""),
        "estadio": (t.get("venue") or {}).get("name", ""),
        "dt":      (t.get("manager") or {}).get("name", ""),
    }


def team_players(team_id: int) -> list[dict]:
    data = _get(f"https://api.sofascore.com/api/v1/team/{team_id}/players")
    if not data:
        return []
    out = []
    for item in data.get("players", []):
        p = item.get("player", {})
        out.append({
            "nombre":   p.get("name", ""),
            "camiseta": p.get("jerseyNumber"),
            "posicion": p.get("position", ""),
            "edad":     p.get("age"),
            "pais":     p.get("country", {}).get("name", ""),
        })
    return out


# ── Stats de jugador ──────────────────────────────────────────

def player_info(pid: int) -> dict:
    data = _get(f"https://api.sofascore.com/api/v1/player/{pid}")
    if not data:
        return {}
    p    = data.get("player", {})
    team = p.get("team") or {}
    return {
        "nombre":   p.get("name", ""),
        "posicion": p.get("position", ""),
        "edad":     p.get("age"),
        "altura":   p.get("height"),
        "pie":      p.get("preferredFoot", ""),
        "equipo":   team.get("name", ""),
        "pais":     p.get("country", {}).get("name", ""),
        "valor_mercado": p.get("proposedMarketValue"),
    }


def player_season_stats(pid: int) -> dict:
    data = _get(f"https://api.sofascore.com/api/v1/player/{pid}/statistics/seasons")
    if not data or not data.get("seasons"):
        return {}
    season = data["seasons"][0]
    tid    = (season.get("tournament") or {}).get("id")
    sid    = season.get("year")
    if not tid:
        return {}
    sd = _get(f"https://api.sofascore.com/api/v1/player/{pid}/tournament/{tid}/season/{sid}/statistics/overall")
    if not sd:
        return {}
    s = sd.get("statistics", {})
    return {
        "competencia":   (season.get("tournament") or {}).get("name", ""),
        "partidos":      s.get("appearances", 0),
        "goles":         s.get("goals", 0),
        "asistencias":   s.get("goalAssist", 0),
        "minutos":       s.get("minutesPlayed", 0),
        "amarillas":     s.get("yellowCards", 0),
        "rojas":         s.get("redCards", 0),
        "rating":        round(s.get("rating", 0), 2) if s.get("rating") else None,
        "tiros_al_arco": s.get("onTargetScoringAttempt", 0),
    }


# ─────────────────────────────────────────────────────────────
# CLAUDE — inteligencia
# ─────────────────────────────────────────────────────────────

INTENT_SYSTEM = f"""Interpretás preguntas sobre fútbol y devolvés un JSON para saber qué buscar.
Hoy: {TODAY.strftime('%d/%m/%Y')} (Buenos Aires).

Respondé SOLO con JSON válido (sin markdown, sin texto extra):
{{
  "intents": ["intent1"],
  "query_team": "nombre equipo o null",
  "query_tournament": "nombre torneo/liga o null",
  "query_player": "nombre jugador o null",
  "n": 10
}}

Intents disponibles:
- team_next            → próximos partidos de un equipo
- team_last            → últimos resultados de un equipo
- team_info            → info general + estadio + DT
- team_players         → plantel del equipo
- tournament_next      → próximos partidos de una liga/copa
- tournament_last      → últimos resultados de una liga
- tournament_standings → tabla de posiciones
- tournament_scorers   → goleadores
- tournament_assists   → asistidores
- player_stats         → stats de un jugador

EJEMPLOS:
"¿cuándo juega River?"              → {{"intents":["team_next"],"query_team":"River Plate","query_tournament":null,"query_player":null,"n":8}}
"últimos de Boca"                   → {{"intents":["team_last"],"query_team":"Boca Juniors","query_tournament":null,"query_player":null,"n":8}}
"tabla Liga Profesional"            → {{"intents":["tournament_standings"],"query_team":null,"query_tournament":"Liga Profesional Argentina","query_player":null,"n":20}}
"goleadores Champions"              → {{"intents":["tournament_scorers"],"query_team":null,"query_tournament":"UEFA Champions League","query_player":null,"n":10}}
"stats Messi"                       → {{"intents":["player_stats"],"query_team":null,"query_tournament":null,"query_player":"Lionel Messi","n":1}}
"plantel e info de Vélez"           → {{"intents":["team_info","team_players"],"query_team":"Vélez Sársfield","query_tournament":null,"query_player":null,"n":30}}
"""

RESPONSE_SYSTEM = f"""Sos Scout, asistente de fútbol. Hoy: {TODAY.strftime('%d/%m/%Y')} (Buenos Aires).
Respondé en español rioplatense, claro y directo.
Usá markdown (negrita, listas, tablas) cuando mejore la lectura.
Horarios ya están en hora Argentina. Fechas en formato amigable (hoy, mañana, sábado 5/4).
Si datos = vacío o sin resultados, decilo y sugerí alternativa.
"""


def parse_intent(msg: str, cliente: anthropic.Anthropic) -> dict:
    try:
        r = cliente.messages.create(
            model="claude-opus-4-5", max_tokens=300,
            system=INTENT_SYSTEM,
            messages=[{"role": "user", "content": msg}],
        )
        raw = re.sub(r"^```[a-z]*\n?|```$", "", r.content[0].text.strip()).strip()
        parsed = json.loads(raw)
        # Normalizar siempre a lista
        if "intent" in parsed and "intents" not in parsed:
            parsed["intents"] = [parsed.pop("intent")]
        if isinstance(parsed.get("intents"), str):
            parsed["intents"] = [parsed["intents"]]
        if not isinstance(parsed.get("intents"), list):
            parsed["intents"] = ["team_next"]
        return parsed
    except Exception as e:
        _api_log.append(f"parse_intent error: {e}")
        return {
            "intents": ["team_next"],
            "query_team": msg,
            "query_tournament": None,
            "query_player": None,
            "n": 10,
        }


def fetch_data(intent_data: dict) -> dict:
    global _api_log
    _api_log = []

    intents = intent_data.get("intents", ["team_next"])
    qt      = intent_data.get("query_team")
    qtour   = intent_data.get("query_tournament")
    qp      = intent_data.get("query_player")
    n       = int(intent_data.get("n") or 10)

    result = {"_log": [], "_found": []}

    # ── Resolver equipo ──────────────────────────────────────
    team_id = None
    if qt:
        teams = search_team(qt)
        if teams:
            team_id = teams[0]["id"]
            result["_found"].append(f"🔵 Equipo: **{teams[0]['name']}** ({teams[0]['country']})")
        else:
            result["_found"].append(f"⚠️ No encontré el equipo '{qt}'")

    # ── Resolver torneo ──────────────────────────────────────
    tourn_id, season_id = None, None
    if qtour:
        tours = search_tournament(qtour)
        if tours:
            tourn_id  = tours[0]["id"]
            season_id = get_season(tourn_id)
            result["_found"].append(f"🏆 Competencia: **{tours[0]['name']}** ({tours[0]['country']})")
        else:
            result["_found"].append(f"⚠️ No encontré la competencia '{qtour}'")

    # ── Resolver jugador ─────────────────────────────────────
    player_id = None
    if qp:
        players = search_player(qp)
        if players:
            player_id = players[0]["id"]
            result["_found"].append(
                f"👤 Jugador: **{players[0]['name']}** "
                f"({players[0]['team']}, {players[0]['country']})"
            )
        else:
            result["_found"].append(f"⚠️ No encontré al jugador '{qp}'")

    # ── Ejecutar intents ─────────────────────────────────────
    for intent in intents:

        if intent == "team_next":
            if team_id:
                result["proximos_partidos"] = team_next(team_id, n)
            elif tourn_id and season_id:
                result["proximos_partidos"] = tournament_next(tourn_id, season_id, n)

        elif intent == "team_last":
            if team_id:
                result["resultados_recientes"] = team_last(team_id, n)
            elif tourn_id and season_id:
                result["resultados_recientes"] = tournament_last(tourn_id, season_id, n)

        elif intent == "team_info":
            if team_id:
                result["info_equipo"] = team_info(team_id)

        elif intent == "team_players":
            if team_id:
                result["plantel"] = team_players(team_id)

        elif intent == "tournament_next":
            if tourn_id and season_id:
                result["proximos_partidos"] = tournament_next(tourn_id, season_id, n)
            elif team_id:                          # fallback: proximos del equipo
                result["proximos_partidos"] = team_next(team_id, n)

        elif intent == "tournament_last":
            if tourn_id and season_id:
                result["resultados_recientes"] = tournament_last(tourn_id, season_id, n)
            elif team_id:
                result["resultados_recientes"] = team_last(team_id, n)

        elif intent == "tournament_standings":
            if tourn_id and season_id:
                result["tabla_posiciones"] = standings(tourn_id, season_id)

        elif intent == "tournament_scorers":
            if tourn_id and season_id:
                result["goleadores"] = top_scorers(tourn_id, season_id, n)

        elif intent == "tournament_assists":
            if tourn_id and season_id:
                result["asistidores"] = top_assists(tourn_id, season_id, n)

        elif intent == "player_stats":
            if player_id:
                result["jugador_info"]  = player_info(player_id)
                result["jugador_stats"] = player_season_stats(player_id)

    result["_log"] = _api_log
    return result


def generate_response(msg: str, data: dict, history: list, cliente: anthropic.Anthropic) -> str:
    data_clean = {k: v for k, v in data.items() if not k.startswith("_")}
    data_str   = json.dumps(data_clean, ensure_ascii=False, indent=2)
    if len(data_str) > 12000:
        data_str = data_str[:12000] + "\n...[datos truncados]"

    messages = history[-16:] + [{
        "role":    "user",
        "content": f"Pregunta: {msg}\n\nDatos de SofaScore:\n{data_str}",
    }]
    try:
        r = cliente.messages.create(
            model="claude-opus-4-5", max_tokens=1500,
            system=RESPONSE_SYSTEM,
            messages=messages,
        )
        return r.content[0].text.strip()
    except Exception as e:
        return f"Error generando respuesta: {e}"


# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────

col_logo, col_date = st.columns([3, 1])
with col_logo:
    st.markdown('<div class="scout-logo">🔬 Scout</div>', unsafe_allow_html=True)
    st.markdown('<div class="scout-sub">Fútbol · SofaScore en tiempo real</div>', unsafe_allow_html=True)
with col_date:
    st.markdown(
        f"<div style='text-align:right;font-size:.75rem;color:#999;padding-top:.4rem'>"
        f"{TODAY.strftime('%d/%m/%Y')}<br>Buenos Aires</div>",
        unsafe_allow_html=True,
    )
st.markdown("<hr style='border:none;border-top:2px solid #c0392b;margin:.4rem 0 1rem'>", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuración")

    if _secret_key:
        api_key = _secret_key
        st.success("🔑 API Key cargada desde secrets", icon="✅")
    else:
        raw = st.text_input("🔑 Anthropic API Key", type="password", placeholder="sk-ant-api03-...")
        api_key = raw.strip() if raw else ""
        if api_key:
            if api_key.startswith("sk-ant-"):
                st.success("✅ Key válida")
            else:
                st.error("⚠️ Formato incorrecto")

    st.divider()
    show_debug = st.toggle("🐛 Mostrar log de API", value=False)
    st.divider()

    st.markdown("### 💡 Ejemplos")
    grupos = {
        "⚽ Equipos": [
            "¿Cuándo juega River?",
            "Últimos resultados de Boca",
            "Plantel e info de Vélez",
            "Stats del equipo Racing Club",
        ],
        "🏆 Ligas": [
            "Tabla de la Liga Profesional Argentina",
            "Próximos partidos de la Champions League",
            "Resultados de la Premier League",
            "Goleadores de la Copa Libertadores",
            "Tabla de La Liga española",
        ],
        "👤 Jugadores": [
            "Estadísticas de Messi",
            "Stats de Lautaro Martínez",
            "Info sobre Julián Álvarez",
        ],
    }
    for grupo, ejemplos in grupos.items():
        st.markdown(f"**{grupo}**")
        for e in ejemplos:
            if st.button(e, key=f"ej_{e}", use_container_width=True):
                st.session_state["preset"] = e

    st.divider()
    if st.button("🗑️ Nueva conversación", use_container_width=True):
        st.session_state.pop("messages", None)
        st.session_state.pop("claude_history", None)
        st.rerun()

# ── Estado ───────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "claude_history" not in st.session_state:
    st.session_state["claude_history"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Input ─────────────────────────────────────────────────────
preset     = st.session_state.pop("preset", None)
user_input = st.chat_input("Preguntá sobre partidos, resultados, tablas, jugadores...")
if preset:
    user_input = preset

if user_input:
    if not api_key or not api_key.startswith("sk-ant-"):
        st.error("⚠️ Ingresá tu API Key de Anthropic en el panel lateral.")
        st.stop()

    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("🔎 Consultando SofaScore..."):
            cliente     = anthropic.Anthropic(api_key=api_key)
            intent_data = parse_intent(user_input, cliente)
            data        = fetch_data(intent_data)

        for found in data.get("_found", []):
            st.caption(found)

        if show_debug:
            with st.expander("🐛 Log llamadas SofaScore", expanded=False):
                for line in data.get("_log", []):
                    st.markdown(f'<div class="debug-box">{line}</div>', unsafe_allow_html=True)
            with st.expander("🧠 Intent detectado", expanded=False):
                st.json({k: v for k, v in intent_data.items()})

        with st.spinner("✍️ Generando respuesta..."):
            response = generate_response(
                user_input, data,
                st.session_state["claude_history"],
                cliente,
            )

        st.markdown(response)

    st.session_state["messages"].append({"role": "assistant", "content": response})
    st.session_state["claude_history"] += [
        {"role": "user",      "content": user_input},
        {"role": "assistant", "content": response},
    ]
    if len(st.session_state["claude_history"]) > 20:
        st.session_state["claude_history"] = st.session_state["claude_history"][-20:]

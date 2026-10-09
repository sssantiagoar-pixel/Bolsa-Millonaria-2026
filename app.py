# -*- coding: utf-8 -*-
"""
=============================================================================
 SIMULADOR "BOLSA MILLONARIA" BVC × TRII  —  app.py
=============================================================================
Simulador local de trading (paper trading) en Streamlit para ensayar 30 días
antes del concurso "Bolsa Millonaria" de la BVC y Trii.

Módulos (pestañas):
  1. Dashboard & Órdenes   -> motor de portafolio, ticket de órdenes, KPIs,
                              posiciones, historial de transacciones.
  2. Estrategias & Riesgo  -> calculadora de break-even, señales cuantitativas
                              (ROC 5/10, Donchian 20, fuerza relativa vs COLCAP).
  3. Backtesting 30D       -> ventanas móviles de ~30 días calendario (21 ruedas)
                              sobre los últimos 6 meses.
  4. Portafolio Óptimo     -> Monte Carlo (frontera eficiente) y Black-Litterman,
                              métricas de rentabilidad/riesgo y capital por acción.
  5. Macro                 -> referencias de solo lectura (COLCAP, Brent, USD/COP…).
  6. Bitácora              -> genera la entrada diaria de journaling en Markdown.

Parámetros del concurso:
  * Capital inicial: $100.000.000 COP
  * Comisión plana Trii Pro: $7.437,50 COP por orden (compra y venta)
  * Horizonte: ~20 días bursátiles

Ejecutar:   streamlit run app.py
Requiere:   streamlit, yfinance, pandas, numpy, scipy, plotly
=============================================================================
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


# -----------------------------------------------------------------------------
# AUTO-LANZADOR: si el archivo se ejecuta con "python app.py", con el botón ▶ de
# Spyder/VS Code o desde Jupyter, Streamlit corre en "modo desnudo" y NO muestra
# nada. Aquí detectamos ese caso y relanzamos con "streamlit run" (abre el navegador).
# -----------------------------------------------------------------------------
def _running_inside_streamlit() -> bool:
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            return get_script_run_ctx() is not None
        except Exception:
            return True  # ante la duda, no relanzar


if __name__ == "__main__" and not _running_inside_streamlit():
    import subprocess
    import sys
    print("▶ Iniciando la interfaz con 'streamlit run'… (se abrirá http://localhost:8501)")
    print("  Para detenerla presiona Ctrl + C en esta consola.")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve()),
                    "--server.headless", "false"])
    sys.exit(0)

try:
    import yfinance as yf
except ImportError:  # la app sigue funcionando con precios manuales
    yf = None

try:
    from scipy.optimize import minimize
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False


# =============================================================================
# 0. CONFIGURACIÓN GENERAL Y CONSTANTES DEL CONCURSO
# =============================================================================
st.set_page_config(page_title="Simulador Bolsa Millonaria", page_icon="📈", layout="wide")

INITIAL_CAPITAL = 100_000_000.0     # Capital ficticio inicial (COP)
COMMISSION = 7_437.50               # Comisión plana Trii Pro por orden (COP)
TRADING_DAYS = 252                  # Ruedas por año (anualización)
CONTEST_DAYS = 20                   # Horizonte del concurso (ruedas)
STATE_FILE = Path(__file__).with_name("portafolio_simulador.json")  # autoguardado (solo local)

# Modo compartido (multiusuario): en Streamlit Community Cloud el código vive en /mount/src.
# Ahí se desactiva el archivo JSON común y cada visitante tiene su portafolio en st.session_state
# (se conserva con Exportar/Importar JSON). Se puede forzar con la variable BM_SHARED_MODE=1.
import os
SHARED_MODE = (Path(__file__).resolve().as_posix().startswith("/mount/src")
               or os.environ.get("BM_SHARED_MODE", "").strip() in ("1", "true", "True"))

# Acciones locales (BVC) clasificadas por sector -> {ticker: nombre}
# Verificadas en Yahoo Finance el 2026-10-08. BCOLOMBIA.CL / PFBCOLOM(B).CL ya no tienen
# datos: Bancolombia cotiza ahora como Grupo Cibest (CIBEST.CL / PFCIBEST.CL).
BVC_SECTORS = {
    "Energía y Petróleo": {
        "ECOPETROL.CL": "Ecopetrol",
        "GEB.CL": "Grupo Energía Bogotá",
        "ISA.CL": "ISA (Interconexión Eléctrica)",
        "CELSIA.CL": "Celsia",
        "PROMIGAS.CL": "Promigas",
        "TERPEL.CL": "Terpel",
    },
    "Financiero y Holdings": {
        "CIBEST.CL": "Grupo Cibest (Bancolombia) Ord.",
        "PFCIBEST.CL": "Grupo Cibest (Bancolombia) Pref.",
        "BOGOTA.CL": "Banco de Bogotá",
        "GRUPOAVAL.CL": "Grupo Aval Ord.",
        "PFAVAL.CL": "Grupo Aval Pref.",
        "GRUPOSURA.CL": "Grupo Sura Ord.",
        "PFGRUPSURA.CL": "Grupo Sura Pref.",
        "PFDAVVNDA.CL": "Davivienda Pref.",
        "PFDAVIGRP.CL": "Grupo Davivienda Pref.",
        "CORFICOLCF.CL": "Corficolombiana Ord.",
        "PFCORFICOL.CL": "Corficolombiana Pref.",
        "GRUBOLIVAR.CL": "Grupo Bolívar",
        "VILLAS.CL": "Banco AV Villas",
        "BVC.CL": "Bolsa de Valores de Colombia",
        "BHI.CL": "BAC Holding International",
        "BMC.CL": "Bolsa Mercantil de Colombia",
    },
    "Industrial y Materiales": {
        "GRUPOARGOS.CL": "Grupo Argos Ord.",
        "PFGRUPOARG.CL": "Grupo Argos Pref.",
        "CEMARGOS.CL": "Cementos Argos Ord.",
        "PFCEMARGOS.CL": "Cementos Argos Pref.",
        "CONCONCRET.CL": "Constructora Conconcreto",
        "ENKA.CL": "Enka de Colombia",
        "FABRICATO.CL": "Fabricato",
    },
    "Consumo y Telecomunicaciones": {
        "NUTRESA.CL": "Grupo Nutresa",
        "EXITO.CL": "Grupo Éxito",
        "MINEROS.CL": "Mineros",
        "ETB.CL": "ETB (Telecomunicaciones de Bogotá)",
    },
    "Inmobiliario y Otros": {
        "PEI.CL": "PEI (Estrategias Inmobiliarias)",
        "CORFERIAS.CL": "Corferias",
    },
    "ETF / Índice": {
        "ICOLCAP.CL": "ETF iShares COLCAP",
        "TEVAICOL.CL": "ETF BTG Pactual TEVA Equity Colombia",  # listado sep-2026: poca historia
    },
}
LOCAL_STOCKS = {t: n for sec in BVC_SECTORS.values() for t, n in sec.items()}
SECTOR_OF = {t: s for s, sec in BVC_SECTORS.items() for t in sec}

# Mercado Global Colombiano (MGC) -> (nombre, subyacente en EE.UU. para proxy)
# Si Yahoo no tiene el ticker .CL, se construye un PROXY = precio USA × USD/COP.
MGC_STOCKS = {
    "TSLACO.CL": ("Tesla (MGC)", "TSLA"),
    "NVDACO.CL": ("NVIDIA (MGC)", "NVDA"),
    "AAPLCO.CL": ("Apple (MGC)", "AAPL"),
    "MSFTCO.CL": ("Microsoft (MGC)", "MSFT"),
    "AMZNCO.CL": ("Amazon (MGC)", "AMZN"),
    "GOOGLCO.CL": ("Alphabet (MGC)", "GOOGL"),
    "METACO.CL": ("Meta (MGC)", "META"),
}

DEFAULT_LOCAL = ["ECOPETROL.CL", "PFCIBEST.CL", "CIBEST.CL", "ISA.CL", "GEB.CL",
                 "GRUPOARGOS.CL", "PFGRUPSURA.CL", "CEMARGOS.CL", "CELSIA.CL",
                 "PFAVAL.CL", "PFDAVVNDA.CL", "CORFICOLCF.CL", "ICOLCAP.CL"]
DEFAULT_MGC = ["TSLACO.CL", "NVDACO.CL", "AAPLCO.CL"]

# Referencias macro (solo lectura). Lista de candidatos: se usa el primero que responda.
MACRO_TICKERS = {
    "COLCAP": ["^COLCAP", "ICOLCAP.CL"],   # Yahoo no publica ^COLCAP -> se usa el ETF ICOLCAP
    "Brent": ["BZ=F"],
    "USD/COP": ["COP=X", "USDCOP=X"],
    "WTI": ["CL=F"],
    "S&P 500": ["^GSPC"],
    "DXY": ["DX-Y.NYB"],
    "UST 10Y (%)": ["^TNX"],
}
FX_CANDIDATES = ["COP=X", "USDCOP=X"]

NAMES = {**LOCAL_STOCKS, **{k: v[0] for k, v in MGC_STOCKS.items()}}


# =============================================================================
# 1. UTILIDADES: FORMATO, COMPATIBILIDAD DE VERSIONES, RENDIMIENTOS
# =============================================================================
def fmt_cop(x, dec: int = 0) -> str:
    """Formato pesos colombianos: $1.234.567,50"""
    if x is None or (isinstance(x, (float, np.floating)) and not np.isfinite(x)):
        return "—"
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-${s}" if x < 0 else f"${s}"


def fmt_pct(x, dec: int = 2) -> str:
    if x is None or (isinstance(x, (float, np.floating)) and not np.isfinite(x)):
        return "—"
    return f"{x * 100:.{dec}f}%".replace(".", ",")


def fmt_num(x, dec: int = 2) -> str:
    if x is None or (isinstance(x, (float, np.floating)) and not np.isfinite(x)):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def label(t: str) -> str:
    return f"{t} · {NAMES.get(t, t)}"


def _stretch_kwargs(func) -> dict:
    """Ancho completo compatible con Streamlit viejo (use_container_width) y nuevo (width='stretch')."""
    try:
        params = inspect.signature(func).parameters
        w = params.get("width")
        if w is not None and isinstance(w.default, str):
            return {"width": "stretch"}
        if "use_container_width" in params:
            return {"use_container_width": True}
    except Exception:
        pass
    return {}


_DF_KW = _stretch_kwargs(st.dataframe)
_CHART_KW = _stretch_kwargs(st.plotly_chart)


def show_df(df, **kw):
    st.dataframe(df, **{**_DF_KW, **kw})


def show_chart(fig, key=None):
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, key=key, **_CHART_KW)


def rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:  # Streamlit < 1.27
        st.experimental_rerun()


def pct(obj):
    """Rendimiento simple día a día (robusto a versiones de pandas)."""
    return obj / obj.shift(1) - 1


def flash(kind: str, msg: str):
    """Mensaje que sobrevive al st.rerun()."""
    st.session_state["_flash"] = (kind, msg)


# =============================================================================
# 2. CAPA DE DATOS (yfinance) CON MANEJO ROBUSTO DE ERRORES
# =============================================================================
def _clean_ohlc(df) -> pd.DataFrame | None:
    """Normaliza un OHLCV: índice sin zona horaria, sin duplicados, sin precios <= 0."""
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    if "Close" not in df.columns:
        return None
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    for c in ["Open", "High", "Low"]:
        if c not in df.columns:
            df[c] = df["Close"]
        df[c] = df[c].fillna(df["Close"])
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df if len(df) >= 5 else None


def _fetch_one(ticker: str, period: str) -> pd.DataFrame | None:
    """Descarga individual con try/except (fallback del batch)."""
    if yf is None:
        return None
    try:
        df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
        return _clean_ohlc(df)
    except Exception:
        return None


def _build_mgc_proxy(us_ticker: str, period: str) -> pd.DataFrame | None:
    """Proxy MGC en COP = OHLC del subyacente USA × tasa USD/COP del día."""
    us = _fetch_one(us_ticker, period)
    if us is None:
        return None
    fx = None
    for c in FX_CANDIDATES:
        fx = _fetch_one(c, period)
        if fx is not None:
            break
    if fx is None:
        return None
    rate = fx["Close"].reindex(us.index.union(fx.index)).ffill().reindex(us.index).bfill()
    out = us.copy()
    for c in ["Open", "High", "Low", "Close"]:
        out[c] = us[c] * rate
    return _clean_ohlc(out)


@st.cache_data(ttl=600, show_spinner=False)
def download_universe(tickers: tuple, period: str = "2y"):
    """Descarga en lote; reintenta individualmente; para MGC usa proxy si falla.
    Retorna (dict ticker->OHLCV, dict ticker->estado)."""
    data, status = {}, {}
    batch = {}
    if yf is not None and tickers:
        try:
            raw = yf.download(list(tickers), period=period, interval="1d", auto_adjust=True,
                              group_by="ticker", progress=False, threads=True)
            if raw is not None and not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    lvl0 = set(raw.columns.get_level_values(0))
                    for t in tickers:
                        if t in lvl0:
                            batch[t] = _clean_ohlc(raw[t])
                elif len(tickers) == 1:
                    batch[tickers[0]] = _clean_ohlc(raw)
        except Exception:
            pass  # cae a descargas individuales

    for t in tickers:
        df = batch.get(t)
        if df is None:
            df = _fetch_one(t, period)
        if df is not None:
            data[t] = df
            status[t] = "✅ OK (yfinance)"
            continue
        if t in MGC_STOCKS:
            us = MGC_STOCKS[t][1]
            proxy = _build_mgc_proxy(us, period)
            if proxy is not None:
                data[t] = proxy
                status[t] = f"⚠️ PROXY {us} × USD/COP"
                continue
        status[t] = "❌ Sin datos (usa precio manual)"
    return data, status


@st.cache_data(ttl=600, show_spinner=False)
def download_macro(period: str = "2y"):
    """Referencias macro de solo lectura. Retorna dict nombre -> (ticker usado, OHLCV)."""
    out = {}
    for name, candidates in MACRO_TICKERS.items():
        for c in candidates:
            df = _fetch_one(c, period)
            if df is not None and len(df) > 30:
                out[name] = (c, df)
                break
    return out


def build_panel(data: dict, tickers, field: str) -> pd.DataFrame:
    frames = {t: data[t][field] for t in tickers if t in data}
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index()


# =============================================================================
# 3. MOTOR DEL PORTAFOLIO (st.session_state + autoguardado JSON)
# =============================================================================
STATE_KEYS = ["cash", "positions", "transactions", "equity_log", "start_date", "journal"]


def _default_state() -> dict:
    return {
        "cash": INITIAL_CAPITAL,
        "positions": {},          # ticker -> {"qty": int, "avg_cost": float (incluye comisión de compra)}
        "transactions": [],       # lista de dicts
        "equity_log": {},         # "YYYY-MM-DD" -> patrimonio
        "start_date": dt.date.today().isoformat(),
        "journal": {},            # "YYYY-MM-DD" -> notas del día
    }


def load_state_file() -> dict | None:
    if SHARED_MODE:   # en la nube cada usuario arranca con su propio portafolio en memoria
        return None
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def save_state():
    """Persistencia en disco: sobrevive a recargas del navegador / reinicios (solo uso local)."""
    if SHARED_MODE:   # nunca escribir un archivo común a todos los usuarios del servidor
        return
    try:
        payload = {k: st.session_state[k] for k in STATE_KEYS}
        STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                              encoding="utf-8")
    except Exception as e:
        st.session_state["_save_error"] = str(e)


def init_state(force_reset: bool = False):
    if st.session_state.get("_initialized") and not force_reset:
        return
    defaults = _default_state()
    loaded = None if force_reset else load_state_file()
    for k, v in defaults.items():
        st.session_state[k] = loaded.get(k, v) if isinstance(loaded, dict) else v
    st.session_state["cash"] = float(st.session_state["cash"])
    st.session_state["_initialized"] = True
    if force_reset:
        save_state()


def execute_order(ticker: str, side: str, qty: int, price: float, note: str = "") -> tuple[bool, str]:
    """Ejecuta una orden con comisión plana descontada inmediatamente del efectivo.
    El costo promedio incluye la comisión de compra -> el PnL no realizado ya es neto."""
    ss = st.session_state
    qty = int(qty)
    if qty <= 0:
        return False, "La cantidad debe ser mayor que cero."
    if price is None or not np.isfinite(price) or price <= 0:
        return False, "Precio inválido. Activa 'precio manual' si el ticker no tiene datos."
    gross = qty * price
    positions = ss["positions"]
    pos = positions.get(ticker, {"qty": 0, "avg_cost": 0.0})
    realized = 0.0

    if side == "COMPRA":
        total = gross + COMMISSION
        if total > ss["cash"] + 1e-6:
            return False, (f"Efectivo insuficiente: necesitas {fmt_cop(total, 2)} y tienes "
                           f"{fmt_cop(ss['cash'], 2)}.")
        ss["cash"] -= total
        new_qty = pos["qty"] + qty
        pos["avg_cost"] = (pos["qty"] * pos["avg_cost"] + gross + COMMISSION) / new_qty
        pos["qty"] = new_qty
        positions[ticker] = pos
        cash_flow = -total
    else:  # VENTA
        if qty > pos["qty"]:
            return False, f"No puedes vender {qty}: posición actual {pos['qty']} acciones."
        total = gross - COMMISSION
        if ss["cash"] + total < 0:
            return False, "La comisión supera el producto de la venta y no hay efectivo para cubrirla."
        ss["cash"] += total
        realized = (price - pos["avg_cost"]) * qty - COMMISSION
        pos["qty"] -= qty
        if pos["qty"] == 0:
            positions.pop(ticker, None)
        else:
            positions[ticker] = pos
        cash_flow = total

    ss["transactions"].append({
        "Fecha": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Ticker": ticker,
        "Operación": side,
        "Cantidad": qty,
        "Precio Ejecutado": float(price),
        "Valor Bruto": float(gross),
        "Comisión": COMMISSION,
        "Total Neto": float(abs(total)),
        "Flujo de Caja": float(cash_flow),
        "PnL Realizado": float(realized),
        "Nota": note,
    })
    save_state()
    verb = "Compradas" if side == "COMPRA" else "Vendidas"
    return True, f"{verb} {qty:,} {ticker} @ {fmt_cop(price, 2)} · comisión {fmt_cop(COMMISSION, 2)}"


def portfolio_snapshot(prices: dict) -> dict:
    ss = st.session_state
    rows, mv, stale = [], 0.0, []
    for t, p in ss["positions"].items():
        last = prices.get(t)
        if last is None or not np.isfinite(last):
            last = p["avg_cost"]
            stale.append(t)
        value = p["qty"] * last
        mv += value
        rows.append({"Ticker": t, "Nombre": NAMES.get(t, t), "Cantidad": p["qty"],
                     "Costo Prom. (c/comisión)": p["avg_cost"], "Último Precio": last,
                     "Valor Mercado": value, "PnL No Realizado": (last - p["avg_cost"]) * p["qty"],
                     "Rent. %": last / p["avg_cost"] - 1 if p["avg_cost"] else np.nan})
    equity = ss["cash"] + mv
    pos_df = pd.DataFrame(rows)
    if not pos_df.empty:
        pos_df["Peso %"] = pos_df["Valor Mercado"] / equity
    tx = pd.DataFrame(ss["transactions"])
    comm_paid = float(tx["Comisión"].sum()) if not tx.empty else 0.0
    realized = float(tx["PnL Realizado"].sum()) if not tx.empty else 0.0
    return {"cash": ss["cash"], "mv": mv, "equity": equity, "pnl": equity - INITIAL_CAPITAL,
            "ret": equity / INITIAL_CAPITAL - 1, "positions": pos_df, "stale": stale,
            "comm_paid": comm_paid, "realized": realized, "n_orders": len(tx)}


def record_equity(equity: float):
    today = dt.date.today().isoformat()
    log = st.session_state["equity_log"]
    if abs(log.get(today, -1) - equity) > 1:
        log[today] = round(float(equity), 2)
        save_state()


# =============================================================================
# 4. ESTRATEGIAS CUANTITATIVAS: SEÑALES
# =============================================================================
def compute_signals(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                    bench: pd.Series | None, rf_annual: float,
                    volume: pd.DataFrame | None = None, min_liq: float = 0.0) -> pd.DataFrame:
    """ROC 5/10, Donchian 20, fuerza relativa y alfa de Jensen (60 ruedas) vs COLCAP,
    más liquidez (monto promedio negociado en 20 ruedas)."""
    rf_d = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    b_full = bench.reindex(close.index).ffill() if bench is not None else None
    rows = []
    for t in close.columns:
        s = close[t].dropna()
        if len(s) < 25:
            continue
        h = high[t].reindex(s.index).fillna(s) if t in high else s
        l = low[t].reindex(s.index).fillna(s) if t in low else s
        last = float(s.iloc[-1])
        roc5 = last / s.iloc[-6] - 1
        roc10 = last / s.iloc[-11] - 1
        roc20 = last / s.iloc[-21] - 1
        up20 = float(h.iloc[-21:-1].max())   # máximo de las 20 ruedas PREVIAS
        lo20 = float(l.iloc[-21:-1].min())
        r = pct(s).dropna()
        vol20 = r.iloc[-20:].std() * math.sqrt(TRADING_DAYS)
        rs20 = alpha = beta = np.nan
        if b_full is not None:
            b = b_full.reindex(s.index)
            if b.notna().sum() > 30 and np.isfinite(b.iloc[-1]) and np.isfinite(b.iloc[-21]):
                rs20 = roc20 - (b.iloc[-1] / b.iloc[-21] - 1)
                df = pd.concat([r.rename("p"), pct(b).rename("b")], axis=1, join="inner").dropna().iloc[-60:]
                if len(df) > 20 and df["b"].var() > 0:
                    beta = df["p"].cov(df["b"]) / df["b"].var()
                    alpha = ((df["p"].mean() - rf_d) - beta * (df["b"].mean() - rf_d)) * TRADING_DAYS
        # Liquidez: monto promedio diario (precio × volumen) y ruedas sin negociación (últimas 20)
        liq = no_trade = np.nan
        if volume is not None and t in volume:
            v = volume[t].reindex(s.index).fillna(0).iloc[-20:]
            liq = float((v * s.iloc[-20:]).mean())
            no_trade = int((v <= 0).sum())
        rows.append({"Ticker": t, "Nombre": NAMES.get(t, t), "Sector": SECTOR_OF.get(t, "MGC / Otro"),
                     "Precio": last,
                     "ROC 5": roc5, "ROC 10": roc10, "ROC 20": roc20,
                     "Donchian Sup. 20": up20, "Donchian Inf. 20": lo20,
                     "Dist. a Máx 20": last / up20 - 1, "Ruptura": last > up20,
                     "FR 20d vs COLCAP": rs20, "Alfa (anual)": alpha, "Beta": beta,
                     "Vol. 20d (anual)": vol20, "Monto prom. 20d (COP)": liq,
                     "Ruedas sin negociar (20d)": no_trade})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("Ticker")
    ranks = df[["ROC 5", "ROC 10", "FR 20d vs COLCAP", "Alfa (anual)"]].rank(pct=True).fillna(0.5)
    df["Score"] = 100 * (0.25 * ranks["ROC 5"] + 0.25 * ranks["ROC 10"]
                         + 0.25 * ranks["FR 20d vs COLCAP"] + 0.25 * ranks["Alfa (anual)"]) \
        + 10 * df["Ruptura"].astype(float)

    df["Ilíquida"] = (df["Monto prom. 20d (COP)"] < min_liq) | (df["Ruedas sin negociar (20d)"] >= 8)

    def _signal(row):
        if row["Ilíquida"]:
            return "⚪ ILÍQUIDA (precaución)"   # precios poco confiables / difícil salir
        if row["Ruptura"] and row["ROC 10"] > 0:
            return "🟢 COMPRA (ruptura Donchian)"
        if row["Score"] >= 65 and row["ROC 10"] > 0 and not (row["FR 20d vs COLCAP"] < 0):
            return "🟢 COMPRA (momentum/alfa)"
        if row["ROC 10"] < 0 and (row["Alfa (anual)"] < 0 or np.isnan(row["Alfa (anual)"])):
            return "🔴 EVITAR / SALIR"
        return "🟡 NEUTRAL"

    df["Señal"] = df.apply(_signal, axis=1)
    df = df.sort_values("Score", ascending=False)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df


# =============================================================================
# 5. MOTOR DE BACKTESTING (ventanas móviles de 30 días / 21 ruedas, últimos 6 meses)
# =============================================================================
def run_backtest(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                 bench: pd.Series | None, top_n: int = 3, hold: int = 21, step: int = 5,
                 lookback_days: int = 126, capital: float = INITIAL_CAPITAL) -> pd.DataFrame:
    """Cada ventana: señal con datos hasta t-1, entrada al cierre de t, salida al cierre de t+hold.
    Todas las estrategias pagan COMMISSION por cada orden (entrada y salida)."""
    close = close.ffill(limit=5)
    high = high.reindex_like(close).fillna(close)
    low = low.reindex_like(close).fillna(close)
    idx = close.index
    n = len(idx)
    if n < lookback_days + 30:
        lookback_days = max(n - 30, 0)
    roc5 = close / close.shift(5) - 1
    roc10 = close / close.shift(10) - 1
    ret20 = close / close.shift(20) - 1
    upper = high.rolling(20).max().shift(1)    # Donchian superior (20 previas)
    lower = low.rolling(10).min().shift(1)     # salida: mínimo de 10 previas
    b = bench.reindex(idx).ffill() if bench is not None else None
    bret20 = (b / b.shift(20) - 1) if b is not None else None

    C, U, L = close.values, upper.values, lower.values
    cols = list(close.columns)

    def basket(picks, fwd):
        if len(picks) == 0:
            return 0.0, 0
        alloc = capital / len(picks)
        pnl = float((alloc * fwd[picks]).sum()) - 2 * len(picks) * COMMISSION
        return pnl / capital, 2 * len(picks)

    def donchian(i, j, valid_mask):
        alloc = capital / top_n
        open_pos, pnl, trades = {}, 0.0, 0
        for k in range(i, j + 1):
            # salidas: ruptura bajista del canal de 10 o fin de ventana
            for c in list(open_pos):
                pxk = C[k, c]
                if k == j or (np.isfinite(L[k, c]) and pxk < L[k, c]):
                    pnl += alloc * (pxk / open_pos[c] - 1) - COMMISSION
                    trades += 1
                    del open_pos[c]
            # entradas: cierre > máximo de 20 ruedas previas
            if k < j and len(open_pos) < top_n:
                cands = []
                for c in range(len(cols)):
                    if valid_mask[c] and c not in open_pos and np.isfinite(U[k, c]) and C[k, c] > U[k, c]:
                        cands.append((C[k, c] / U[k, c] - 1, c))
                for _, c in sorted(cands, reverse=True):
                    if len(open_pos) >= top_n:
                        break
                    open_pos[c] = C[k, c]
                    pnl -= COMMISSION
                    trades += 1
        return pnl / capital, trades

    records = []
    start = max(n - lookback_days, 25)
    for i in range(start, n - hold, step):
        j = i + hold
        valid = close.iloc[i].notna() & close.iloc[j].notna() & close.iloc[i - 20].notna()
        if valid.sum() == 0:
            continue
        fwd = close.iloc[j] / close.iloc[i] - 1
        rec = {"Inicio": idx[i].date(), "Fin": idx[j].date()}

        mom = (0.5 * roc5.iloc[i - 1] + 0.5 * roc10.iloc[i - 1])[valid].dropna()
        rec["Momentum ROC"], rec["_tr_mom"] = basket(mom[mom > 0].nlargest(top_n).index, fwd)

        if bret20 is not None and np.isfinite(bret20.iloc[i - 1]):
            rs = (ret20.iloc[i - 1] - bret20.iloc[i - 1])[valid].dropna()
        else:
            rs = ret20.iloc[i - 1][valid].dropna()
        rec["Fuerza Relativa"], rec["_tr_rs"] = basket(rs[rs > 0].nlargest(top_n).index, fwd)

        rec["Donchian 20"], rec["_tr_don"] = donchian(i, j, valid.values)

        if b is not None and np.isfinite(b.iloc[i]) and np.isfinite(b.iloc[j]):
            rec["B&H COLCAP"] = (capital * (b.iloc[j] / b.iloc[i] - 1) - 2 * COMMISSION) / capital
        else:
            rec["B&H COLCAP"] = np.nan
        rec["B&H Equiponderado"], _ = basket(valid[valid].index, fwd)
        records.append(rec)
    return pd.DataFrame(records)


def summarize_backtest(bt: pd.DataFrame) -> pd.DataFrame:
    strats = ["Momentum ROC", "Fuerza Relativa", "Donchian 20", "B&H COLCAP", "B&H Equiponderado"]
    trades_map = {"Momentum ROC": "_tr_mom", "Fuerza Relativa": "_tr_rs", "Donchian 20": "_tr_don"}
    rows = []
    for s in strats:
        if s not in bt:
            continue
        x = bt[s].dropna()
        if x.empty:
            continue
        beat = (bt[s] > bt["B&H COLCAP"]).mean() if bt["B&H COLCAP"].notna().any() else np.nan
        rows.append({"Estrategia": s, "Retorno medio": x.mean(), "Mediana": x.median(),
                     "Desv. estándar": x.std(), "Tasa de acierto (>0)": (x > 0).mean(),
                     "Mejor ventana": x.max(), "Peor ventana": x.min(),
                     "Ratio media/desv.": x.mean() / x.std() if x.std() > 0 else np.nan,
                     "% ventanas > COLCAP": beat,
                     "Órdenes prom.": bt[trades_map[s]].mean() if s in trades_map else 2.0})
    return pd.DataFrame(rows).set_index("Estrategia")


# =============================================================================
# 6. OPTIMIZACIÓN DE PORTAFOLIO: MONTE CARLO, BLACK-LITTERMAN Y MÉTRICAS
# =============================================================================
def compute_metrics(port_ret: pd.Series, bench_ret: pd.Series | None, rf_annual: float) -> dict:
    """Métricas de rentabilidad y riesgo sobre rendimientos diarios históricos."""
    r = port_ret.dropna()
    n = len(r)
    if n < 10:
        return {}
    rf_d = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    sd = r.std(ddof=1)
    ex = r - rf_d
    ann_ret = (1 + r).prod() ** (TRADING_DAYS / n) - 1
    ann_vol = sd * math.sqrt(TRADING_DAYS)
    down_dev = math.sqrt((np.minimum(ex, 0) ** 2).mean()) * math.sqrt(TRADING_DAYS)
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    var95 = -float(np.percentile(r, 5))
    tail = r[r <= -var95]
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    m = {
        "Retorno anualizado": ann_ret,
        "Retorno acumulado (ventana)": float(eq.iloc[-1] - 1),
        "Volatilidad anual": ann_vol,
        "Sharpe": ex.mean() / sd * math.sqrt(TRADING_DAYS) if sd > 0 else np.nan,
        "Sortino": ex.mean() * TRADING_DAYS / down_dev if down_dev > 0 else np.nan,
        "Calmar": ann_ret / abs(mdd) if mdd < 0 else np.nan,
        "Omega (umbral 0)": gains / losses if losses > 0 else np.nan,
        "Máximo Drawdown": mdd,
        "VaR 95% diario (hist.)": var95,
        "CVaR 95% diario": -float(tail.mean()) if len(tail) else np.nan,
        "Desviación a la baja (anual)": down_dev,
        "Beta": np.nan, "Alfa de Jensen (anual)": np.nan, "Tracking Error": np.nan,
        "Information Ratio": np.nan, "Treynor": np.nan, "Correlación vs COLCAP": np.nan,
        "R²": np.nan, "Retorno COLCAP (anual)": np.nan,
    }
    if bench_ret is not None:
        df = pd.concat([r.rename("p"), bench_ret.rename("b")], axis=1, join="inner").dropna()
        if len(df) > 10 and df["b"].var() > 0:
            p, b = df["p"], df["b"]
            beta = p.cov(b) / b.var()
            active = p - b
            te = active.std(ddof=1) * math.sqrt(TRADING_DAYS)
            corr = p.corr(b)
            m.update({
                "Beta": beta,
                "Alfa de Jensen (anual)": ((p.mean() - rf_d) - beta * (b.mean() - rf_d)) * TRADING_DAYS,
                "Tracking Error": te,
                "Information Ratio": active.mean() * TRADING_DAYS / te if te > 0 else np.nan,
                "Treynor": (p.mean() - rf_d) * TRADING_DAYS / beta if beta != 0 else np.nan,
                "Correlación vs COLCAP": corr,
                "R²": corr ** 2,
                "Retorno COLCAP (anual)": (1 + b).prod() ** (TRADING_DAYS / len(b)) - 1,
            })
    return m


def project_weights(W: np.ndarray, wmin: float, wmax: float) -> np.ndarray:
    """Proyecta pesos aleatorios a la región factible [wmin, wmax], suma = 1."""
    for _ in range(100):
        W = np.clip(W, wmin, wmax)
        W = W / W.sum(axis=1, keepdims=True)
    ok = (W >= wmin - 1e-6).all(axis=1) & (W <= wmax + 1e-6).all(axis=1)
    return W[ok]


def _sortino_vec(P: np.ndarray, rf_d: float) -> np.ndarray:
    """Sortino anualizado para una matriz de rendimientos (T x m)."""
    ex = P - rf_d
    dd = np.sqrt((np.minimum(ex, 0) ** 2).mean(axis=0)) * math.sqrt(TRADING_DAYS)
    return np.where(dd > 0, ex.mean(axis=0) * TRADING_DAYS / dd, np.nan)


def monte_carlo_portfolios(rets: pd.DataFrame, rf: float, n_sims: int, wmin: float, wmax: float,
                           seed: int = 42):
    """Simula portafolios aleatorios (Dirichlet) -> frontera eficiente."""
    rng = np.random.default_rng(seed)
    n = rets.shape[1]
    mu = rets.mean().values * TRADING_DAYS
    cov = rets.cov().values * TRADING_DAYS
    half = n_sims // 2
    W = np.vstack([rng.dirichlet(np.ones(n), size=half),            # diversificados
                   rng.dirichlet(np.full(n, 0.3), size=n_sims - half)])  # concentrados
    W = project_weights(W, wmin, wmax)
    if len(W) == 0:
        return None, None
    p_ret = W @ mu
    p_vol = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
    rf_d = (1 + rf) ** (1 / TRADING_DAYS) - 1
    P = rets.values @ W.T
    sims = pd.DataFrame({"Retorno": p_ret, "Volatilidad": p_vol,
                         "Sharpe": (p_ret - rf) / p_vol, "Sortino": _sortino_vec(P, rf_d)})
    return sims, W


def black_litterman(cov: np.ndarray, w_prior: np.ndarray, delta: float, tau: float,
                    P: np.ndarray | None, Q: np.ndarray | None, conf: np.ndarray | None):
    """Modelo Black-Litterman (Idzorek para Ω según confianza).
    π = δ Σ w_mkt ;  μ_BL = [(τΣ)^-1 + PᵀΩ^-1P]^-1 [(τΣ)^-1 π + PᵀΩ^-1 Q] ;  Σ_BL = Σ + M"""
    pi = delta * cov @ w_prior
    if P is None or len(Q) == 0:
        return pi, cov, pi
    tauS = tau * cov
    c = np.clip(conf, 0.01, 0.99)
    omega = np.diag([((1 - c[k]) / c[k]) * float(P[k] @ tauS @ P[k]) + 1e-12 for k in range(len(Q))])
    inv_tauS = np.linalg.pinv(tauS)
    inv_omega = np.linalg.pinv(omega)
    M = np.linalg.pinv(inv_tauS + P.T @ inv_omega @ P)
    mu_bl = M @ (inv_tauS @ pi + P.T @ inv_omega @ Q)
    return pi, cov + M, mu_bl


def parse_views(views_df: pd.DataFrame, assets: list):
    """Convierte la tabla de views en matrices P, Q y vector de confianza."""
    P, Q, C, used = [], [], [], []
    if views_df is None or views_df.empty:
        return None, np.array([]), np.array([]), used
    for _, row in views_df.iterrows():
        a = row.get("Activo")
        if a not in assets or pd.isna(row.get("Retorno anual esperado (%)")):
            continue
        p = np.zeros(len(assets))
        p[assets.index(a)] = 1.0
        txt = f"{a} rinde {row['Retorno anual esperado (%)']:.1f}% anual"
        if row.get("Tipo") == "Relativa":
            bb = row.get("Vs. activo")
            if bb not in assets or bb == a:
                continue
            p[assets.index(bb)] = -1.0
            txt = f"{a} supera a {bb} en {row['Retorno anual esperado (%)']:.1f}% anual"
        conf = row.get("Confianza (%)")
        conf = 50.0 if pd.isna(conf) else float(conf)
        P.append(p)
        Q.append(float(row["Retorno anual esperado (%)"]) / 100)
        C.append(conf / 100)
        used.append(f"{txt} (confianza {conf:.0f}%)")
    if not P:
        return None, np.array([]), np.array([]), used
    return np.array(P), np.array(Q), np.array(C), used


def optimize_weights(mu: np.ndarray, cov: np.ndarray, rf: float, objective: str,
                     wmin: float, wmax: float, scen: np.ndarray | None = None,
                     delta: float = 2.5, seed: int = 7) -> np.ndarray:
    """Optimizador long-only con límites por activo (SLSQP; random search si no hay scipy)."""
    n = len(mu)
    rf_d = (1 + rf) ** (1 / TRADING_DAYS) - 1

    def f(w):
        if objective == "Mínima volatilidad":
            return float(w @ cov @ w)
        if objective == "Máximo Sortino" and scen is not None:
            ex = scen @ w - rf_d
            dd = math.sqrt((np.minimum(ex, 0) ** 2).mean()) * math.sqrt(TRADING_DAYS)
            return -(ex.mean() * TRADING_DAYS / dd) if dd > 0 else 0.0
        if objective == "Máxima utilidad (μ − δ/2·σ²)":
            return -float(w @ mu - delta / 2 * w @ cov @ w)
        vol = math.sqrt(max(float(w @ cov @ w), 1e-12))
        return -(float(w @ mu) - rf) / vol  # Máximo Sharpe

    # búsqueda aleatoria inicial (también fallback sin scipy)
    rng = np.random.default_rng(seed)
    W = project_weights(rng.dirichlet(np.ones(n), size=4000), wmin, wmax)
    x0 = np.clip(np.full(n, 1 / n), wmin, wmax)
    x0 = x0 / x0.sum()
    if len(W):
        vals = np.array([f(w) for w in W])
        if vals.min() < f(x0):
            x0 = W[int(np.nanargmin(vals))]
    if not SCIPY_OK:
        return x0
    res = minimize(f, x0, method="SLSQP", bounds=[(wmin, wmax)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-10})
    w = res.x if res.success and f(res.x) <= f(x0) + 1e-9 else x0
    w = np.clip(w, 0, None)
    return w / w.sum()


def allocate_capital(weights: pd.Series, prices: dict, capital: float, min_weight: float = 0.005):
    """Distribuye el capital en acciones enteras descontando una comisión por orden de compra."""
    w = weights[weights >= min_weight]
    w = w / w.sum()
    n = len(w)
    investable = max(capital - n * COMMISSION, 0)
    rows = []
    for t, wt in w.items():
        price = prices.get(t, np.nan)
        target = wt * investable
        shares = int(target // price) if price and np.isfinite(price) and price > 0 else 0
        invested = shares * price if shares else 0.0
        rows.append({"Ticker": t, "Nombre": NAMES.get(t, t), "Peso óptimo": wt,
                     "Capital objetivo": target, "Precio": price, "Acciones": shares,
                     "Capital invertido": invested, "Comisión": COMMISSION if shares else 0.0,
                     "Costo total": invested + (COMMISSION if shares else 0.0),
                     "Comisión / posición": COMMISSION / invested if invested else np.nan})
    df = pd.DataFrame(rows)
    tot_inv = df["Capital invertido"].sum()
    df["Peso real"] = df["Capital invertido"] / tot_inv if tot_inv > 0 else 0.0
    residual = capital - df["Costo total"].sum()
    return df, residual


def simulate_forward(rets: pd.DataFrame, w: np.ndarray, capital: float, horizon: int,
                     n_paths: int, method: str, mu_ann=None, cov_ann=None, seed: int = 11):
    """Simulación Monte Carlo del valor del portafolio a 'horizon' ruedas."""
    rng = np.random.default_rng(seed)
    if method.startswith("Normal") and mu_ann is not None:
        R = rng.multivariate_normal(np.asarray(mu_ann) / TRADING_DAYS, np.asarray(cov_ann) / TRADING_DAYS,
                                    size=(n_paths, horizon))
        pr = R @ w
    else:  # bootstrap histórico conjunto (preserva correlaciones y colas)
        X = rets.values
        pr = X[rng.integers(0, len(X), size=(n_paths, horizon))] @ w
    n_orders = int((w > 0.005).sum())
    start = capital - n_orders * COMMISSION                 # comisiones de compra
    paths = start * np.cumprod(1 + pr, axis=1)
    final = paths[:, -1] - n_orders * COMMISSION              # comisiones de venta
    return paths, final


# =============================================================================
# 7. INICIALIZACIÓN Y BARRA LATERAL
# =============================================================================
init_state()

with st.sidebar:
    st.title("📈 Bolsa Millonaria")
    st.caption("Simulador BVC × Trii · Paper trading")
    start_date = dt.date.fromisoformat(st.session_state["start_date"])
    day_n = int(np.busday_count(start_date, dt.date.today() + dt.timedelta(days=1)))
    st.progress(min(day_n / CONTEST_DAYS, 1.0), text=f"Día bursátil {day_n} de {CONTEST_DAYS}")

    st.subheader("🌎 Universo de activos")
    sel_sectors = st.multiselect("Sectores BVC", list(BVC_SECTORS), default=list(BVC_SECTORS))
    sector_tickers = [t for s in sel_sectors for t in BVC_SECTORS[s]]
    all_sector = st.checkbox("Incluir TODAS las acciones de los sectores elegidos", value=False,
                             help="Útil para escanear todo el mercado en las señales (la 1.ª descarga tarda más).")
    if all_sector:
        sel_local = sector_tickers
        st.caption(f"{len(sel_local)} acciones locales incluidas.")
    else:
        sel_local = st.multiselect("Acciones locales (BVC)", sector_tickers,
                                   default=[t for t in DEFAULT_LOCAL if t in sector_tickers],
                                   format_func=lambda t: f"{label(t)} · {SECTOR_OF.get(t, '')}")
    sel_mgc = st.multiselect("Mercado Global Colombiano (MGC)", list(MGC_STOCKS), default=DEFAULT_MGC,
                             format_func=label)
    extra_txt = st.text_input("Tickers adicionales (separados por coma)", "",
                              help="Ej.: NUTRESA.CL, BHI.CL. Se validan con yfinance.")
    extra = [x.strip().upper() for x in extra_txt.split(",") if x.strip()]

    st.subheader("⚙️ Parámetros")
    rf_annual = st.number_input("Tasa libre de riesgo (% E.A.)", 0.0, 30.0, 9.0, 0.25,
                                help="Referencia: tasa de TES corto plazo / IBR. Ajústala al dato vigente.") / 100
    exp_margin = st.number_input("Margen esperado por operación (%)", 0.1, 50.0, 3.0, 0.5) / 100
    be_threshold = st.number_input("Umbral X%: comisión ida+vuelta máx. sobre ganancia esperada",
                                   1.0, 100.0, 10.0, 1.0) / 100
    min_liq = st.number_input("Liquidez mínima: monto prom. diario 20d (COP)", 0.0, 1e11, 20_000_000.0,
                              5_000_000.0, help="Por debajo de este monto (o con ≥ 8 de 20 ruedas sin "
                                                "negociar) la acción se marca ⚪ ILÍQUIDA y se excluye de "
                                                "la selección automática del portafolio.")

    if st.button("🔄 Actualizar precios"):
        st.cache_data.clear()
        rerun()

    st.subheader("💾 Persistencia")
    if SHARED_MODE:
        st.warning("🌐 Versión web: tu portafolio vive solo en esta pestaña del navegador. "
                   "**Exporta el JSON al terminar** y vuelve a importarlo en tu próxima sesión.")
    else:
        st.caption(f"Autoguardado en `{STATE_FILE.name}`")
    export = {k: st.session_state[k] for k in STATE_KEYS}
    st.download_button("⬇️ Exportar portafolio (JSON)", json.dumps(export, ensure_ascii=False, indent=2, default=str),
                       file_name=f"portafolio_{dt.date.today()}.json", mime="application/json")
    up = st.file_uploader("Importar portafolio (JSON)", type="json")
    if up is not None and st.button("📥 Cargar archivo importado"):
        try:
            loaded = json.loads(up.read().decode("utf-8"))
            for k in STATE_KEYS:
                if k in loaded:
                    st.session_state[k] = loaded[k]
            st.session_state["cash"] = float(st.session_state["cash"])
            save_state()
            flash("success", "Portafolio importado correctamente.")
            rerun()
        except Exception as e:
            st.error(f"Archivo inválido: {e}")
    with st.expander("🧨 Reiniciar simulación"):
        confirm = st.checkbox("Confirmo que quiero borrar posiciones y transacciones")
        if st.button("Reiniciar a $100.000.000", disabled=not confirm):
            init_state(force_reset=True)
            flash("info", "Simulación reiniciada.")
            rerun()

# Universo final (incluye siempre lo que ya está en cartera)
universe = list(dict.fromkeys(sel_local + sel_mgc + extra + list(st.session_state["positions"])))

with st.spinner("Descargando datos de mercado (yfinance)…"):
    data, status = download_universe(tuple(sorted(universe)), "2y")
    macro = download_macro("2y")

close = build_panel(data, universe, "Close").ffill(limit=5)
high = build_panel(data, universe, "High")
low = build_panel(data, universe, "Low")
volume = build_panel(data, universe, "Volume")
last_prices = {t: float(df["Close"].iloc[-1]) for t, df in data.items()}
last_dates = {t: df.index[-1].date() for t, df in data.items()}

bench_ticker, bench = None, None
if "COLCAP" in macro:
    bench_ticker, bench_df = macro["COLCAP"]
    bench = bench_df["Close"].rename("COLCAP")

with st.sidebar.expander("📡 Estado de descarga de datos"):
    show_df(pd.DataFrame({"Estado": status}).rename_axis("Ticker"))
    st.caption(f"Benchmark COLCAP: {bench_ticker or 'NO DISPONIBLE'}")
    if yf is None:
        st.error("yfinance no está instalado: `pip install yfinance`")

signals = compute_signals(close, high, low, bench, rf_annual, volume, min_liq) \
    if not close.empty else pd.DataFrame()

# Mensajes pendientes tras st.rerun()
if "_flash" in st.session_state:
    kind, msg = st.session_state.pop("_flash")
    getattr(st, kind)(msg)
if st.session_state.get("_save_error"):
    st.warning(f"No se pudo autoguardar: {st.session_state.pop('_save_error')}")

st.title("🏆 Simulador Bolsa Millonaria · BVC × Trii")
tabs = st.tabs(["📊 Dashboard & Órdenes", "🧠 Estrategias & Riesgo", "🧪 Backtesting 30D",
                "🎯 Portafolio Óptimo", "🌐 Macro", "📓 Bitácora"])


# =============================================================================
# 8. PESTAÑA 1 — DASHBOARD Y MOTOR DE PORTAFOLIO
# =============================================================================
with tabs[0]:
    snap = portfolio_snapshot(last_prices)
    record_equity(snap["equity"])

    k = st.columns(3) + st.columns(3)   # 2 filas de 3 para que las cifras no se corten
    k[0].metric("💵 Efectivo", fmt_cop(snap["cash"]))
    k[1].metric("📦 Valor de mercado", fmt_cop(snap["mv"]))
    k[2].metric("🏦 Patrimonio total", fmt_cop(snap["equity"]))
    k[3].metric("📈 PnL neto ajustado", fmt_cop(snap["pnl"]), fmt_pct(snap["ret"]))
    k[4].metric("🎯 Rentabilidad", fmt_pct(snap["ret"]))
    k[5].metric("🧾 Comisiones pagadas", fmt_cop(snap["comm_paid"], 2), f"{snap['n_orders']} órdenes",
                delta_color="off")
    if snap["stale"]:
        st.warning(f"Sin precio de mercado para {', '.join(snap['stale'])}: se valoran a costo promedio.")

    col_o, col_p = st.columns([1, 2])

    # ---------------- Ticket de orden ----------------
    with col_o:
        st.subheader("🧾 Ticket de orden")
        tradable = sorted(set(universe))
        if not tradable:
            st.info("Selecciona activos en la barra lateral.")
        else:
            tk = st.selectbox("Activo", tradable, format_func=label, key="ord_ticker")
            side = st.radio("Operación", ["COMPRA", "VENTA"], horizontal=True, key="ord_side")
            px_mkt = last_prices.get(tk)
            if px_mkt:
                st.caption(f"Último precio: **{fmt_cop(px_mkt, 2)}** (cierre/último dato {last_dates[tk]}) · "
                           f"{status.get(tk, '')}")
            manual = st.checkbox("Usar precio manual (p. ej. el que ves en Trii)", value=px_mkt is None,
                                 key=f"ord_manual_{tk}")
            if manual:
                price = st.number_input("Precio de ejecución (COP)", min_value=0.0,
                                        value=float(px_mkt or 0.0), step=10.0, key=f"ord_px_{tk}")
            else:
                price = px_mkt or 0.0

            held = st.session_state["positions"].get(tk, {}).get("qty", 0)
            mode = st.radio("Definir orden por", ["Cantidad", "Monto (COP)"], horizontal=True, key="ord_mode")
            if mode == "Cantidad":
                default_q = held if side == "VENTA" and held else 100
                qty = int(st.number_input("Cantidad de acciones", min_value=0, value=int(default_q), step=1,
                                          key=f"ord_qty_{tk}_{side}"))
            else:
                amount = st.number_input("Monto a invertir/vender (COP)", min_value=0.0, value=10_000_000.0,
                                         step=500_000.0, key="ord_amount")
                if side == "COMPRA":
                    qty = int(max(amount - COMMISSION, 0) // price) if price > 0 else 0
                else:
                    qty = min(int(amount // price), held) if price > 0 else 0
                st.caption(f"Cantidad calculada: **{qty:,}** acciones")
            if side == "VENTA":
                st.caption(f"Posición actual: {held:,} acciones")
            if not signals.empty and tk in signals.index:
                liq_tk = signals.loc[tk, "Monto prom. 20d (COP)"]
                if signals.loc[tk, "Ilíquida"]:
                    st.warning(f"⚪ {tk} es ILÍQUIDA: monto prom. diario {fmt_cop(liq_tk)}, "
                               f"{signals.loc[tk, 'Ruedas sin negociar (20d)']:.0f} de 20 ruedas sin negociar. "
                               "El precio puede no ser ejecutable y salir podría ser difícil.")
                elif np.isfinite(liq_tk) and liq_tk > 0 and qty * price > 0.2 * liq_tk:
                    st.warning(f"La orden equivale al {fmt_pct(qty * price / liq_tk, 0)} del monto diario "
                               f"promedio negociado ({fmt_cop(liq_tk)}): podría mover el precio.")

            gross = qty * price
            if gross > 0:
                total = gross + COMMISSION if side == "COMPRA" else gross - COMMISSION
                st.markdown(
                    f"| Concepto | Valor |\n|---|---|\n"
                    f"| Valor bruto | {fmt_cop(gross, 2)} |\n"
                    f"| Comisión Trii Pro | {fmt_cop(COMMISSION, 2)} |\n"
                    f"| **Total neto** | **{fmt_cop(total, 2)}** |\n"
                    f"| Comisión / orden | {fmt_pct(COMMISSION / gross, 3)} |")
                if side == "COMPRA":
                    rt = 2 * COMMISSION
                    be_move = rt / gross
                    share = rt / (gross * exp_margin)
                    msg = (f"Break-even: el precio debe subir **{fmt_pct(be_move, 3)}** solo para cubrir "
                           f"comisiones de ida y vuelta. Con un margen esperado de {fmt_pct(exp_margin, 1)}, "
                           f"las comisiones consumen **{fmt_pct(share, 1)}** de la ganancia esperada.")
                    if share > be_threshold:
                        st.error("🚨 ORDEN DEMASIADO PEQUEÑA. " + msg +
                                 f" Mínimo recomendado: {fmt_cop(rt / (exp_margin * be_threshold))}.")
                    elif share > be_threshold / 2:
                        st.warning("⚠️ " + msg)
                    else:
                        st.success("✅ " + msg)
                else:
                    pos = st.session_state["positions"].get(tk)
                    if pos:
                        est = (price - pos["avg_cost"]) * min(qty, held) - COMMISSION
                        st.info(f"PnL realizado estimado (neto de comisiones): **{fmt_cop(est)}**")

            note = st.text_input("Nota / razón del trade (va a la bitácora)", key="ord_note")
            if st.button(f"✅ Ejecutar {side}", type="primary", disabled=qty <= 0 or price <= 0):
                ok, msg = execute_order(tk, side, qty, price, note)
                if ok:
                    flash("success", "Orden ejecutada: " + msg)
                    rerun()
                else:
                    st.error(msg)

    # ---------------- Posiciones y evolución ----------------
    with col_p:
        st.subheader("📦 Posiciones abiertas")
        pos_df = snap["positions"]
        if pos_df.empty:
            st.info("Sin posiciones. Todo el capital está en efectivo.")
        else:
            show_df(pos_df.style.format({
                "Costo Prom. (c/comisión)": lambda x: fmt_cop(x, 2), "Último Precio": lambda x: fmt_cop(x, 2),
                "Valor Mercado": fmt_cop, "PnL No Realizado": fmt_cop, "Rent. %": fmt_pct, "Peso %": fmt_pct,
                "Cantidad": "{:,.0f}"}), hide_index=True)
            pie = pd.concat([pos_df[["Ticker", "Valor Mercado"]],
                             pd.DataFrame([{"Ticker": "EFECTIVO", "Valor Mercado": snap["cash"]}])])
            fig = px.pie(pie, names="Ticker", values="Valor Mercado", hole=0.5, title="Composición del patrimonio")
            show_chart(fig, key="pie_dash")

        st.subheader("📈 Evolución del patrimonio")
        log = st.session_state["equity_log"]
        if log:
            eq = pd.Series({pd.Timestamp(st.session_state["start_date"]): INITIAL_CAPITAL})
            eq = pd.concat([eq, pd.Series({pd.Timestamp(k2): v for k2, v in log.items()})])
            eq = eq[~eq.index.duplicated(keep="last")].sort_index()
            fig = go.Figure(go.Scatter(x=eq.index, y=eq.values, mode="lines+markers", name="Simulador"))
            if bench is not None:
                bsub = bench[bench.index >= eq.index[0]]
                if len(bsub) > 1:
                    fig.add_trace(go.Scatter(x=bsub.index, y=INITIAL_CAPITAL * bsub / bsub.iloc[0],
                                             name="COLCAP (base capital)", line=dict(dash="dot")))
            fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash", line_color="gray")
            fig.update_layout(yaxis_title="COP", height=320)
            show_chart(fig, key="equity_curve")

    st.subheader("🧾 Historial de transacciones")
    tx = pd.DataFrame(st.session_state["transactions"])
    if tx.empty:
        st.caption("Aún no hay transacciones.")
    else:
        cols_tx = ["Fecha", "Ticker", "Operación", "Cantidad", "Precio Ejecutado", "Valor Bruto",
                   "Comisión", "Total Neto", "PnL Realizado", "Nota"]
        show_df(tx[cols_tx].iloc[::-1].style.format({
            "Precio Ejecutado": lambda x: fmt_cop(x, 2), "Valor Bruto": lambda x: fmt_cop(x, 2),
            "Comisión": lambda x: fmt_cop(x, 2), "Total Neto": lambda x: fmt_cop(x, 2),
            "PnL Realizado": fmt_cop, "Cantidad": "{:,.0f}"}), hide_index=True)
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Descargar historial (CSV)", tx.to_csv(index=False).encode("utf-8-sig"),
                           file_name="transacciones_simulador.csv", mime="text/csv")
        c2.metric("PnL realizado acumulado (neto)", fmt_cop(snap["realized"]))


# =============================================================================
# 9. PESTAÑA 2 — ESTRATEGIAS Y GESTIÓN DE RIESGO
# =============================================================================
with tabs[1]:
    st.subheader("🧮 Calculadora de Break-Even (comisión fija)")
    b1, b2, b3 = st.columns(3)
    be_amount = b1.number_input("Tamaño de la orden (COP)", 100_000.0, 100_000_000.0, 5_000_000.0, 500_000.0)
    be_margin = b2.number_input("Movimiento esperado (%)", 0.1, 50.0, exp_margin * 100, 0.5, key="be_m") / 100
    be_x = b3.number_input("Umbral X% (comisión / ganancia esperada)", 1.0, 100.0, be_threshold * 100, 1.0,
                           key="be_x") / 100
    rt = 2 * COMMISSION
    exp_profit = be_amount * be_margin
    share = rt / exp_profit
    min_order = rt / (be_margin * be_x)
    m = st.columns(4)
    m[0].metric("Costo ida y vuelta", fmt_cop(rt, 2))
    m[1].metric("Movimiento break-even", fmt_pct(rt / be_amount, 3))
    m[2].metric("Comisión / ganancia esperada", fmt_pct(share, 1))
    m[3].metric("Orden mínima recomendada", fmt_cop(min_order))
    if share > be_x:
        st.error(f"🚨 La comisión fija consume {fmt_pct(share, 1)} del margen esperado (> {fmt_pct(be_x, 0)}). "
                 f"Aumenta la orden a ≥ {fmt_cop(min_order)} o busca movimientos mayores.")
    else:
        st.success(f"✅ Comisión razonable: {fmt_pct(share, 1)} del margen esperado (≤ {fmt_pct(be_x, 0)}).")
    sizes = np.linspace(500_000, 50_000_000, 200)
    fig = go.Figure(go.Scatter(x=sizes, y=100 * rt / (sizes * be_margin), name="Comisión / ganancia (%)"))
    fig.add_hline(y=be_x * 100, line_dash="dash", line_color="red", annotation_text=f"Umbral {be_x * 100:.0f}%")
    fig.add_vline(x=be_amount, line_dash="dot", annotation_text="Tu orden")
    fig.update_layout(xaxis_title="Tamaño de orden (COP)", yaxis_title="% de la ganancia esperada",
                      yaxis_range=[0, min(100, max(30, be_x * 300))], height=300)
    show_chart(fig, key="be_curve")

    st.divider()
    st.subheader("📡 Señales cuantitativas (horizonte 1 mes)")
    st.caption("ROC 5/10 = momentum · Donchian 20 = ruptura sobre el máximo de las 20 ruedas previas · "
               "FR = retorno 20d del activo − COLCAP · Alfa de Jensen y Beta con 60 ruedas. "
               "Score = percentil promedio (ROC5, ROC10, FR, Alfa) + 10 pts si hay ruptura.")
    if signals.empty:
        st.warning("No hay suficientes datos para calcular señales.")
    else:
        pct_cols = ["ROC 5", "ROC 10", "ROC 20", "Dist. a Máx 20", "FR 20d vs COLCAP", "Alfa (anual)",
                    "Vol. 20d (anual)"]
        fmt = {c: fmt_pct for c in pct_cols}
        fmt.update({"Precio": lambda x: fmt_cop(x, 2), "Donchian Sup. 20": lambda x: fmt_cop(x, 2),
                    "Donchian Inf. 20": lambda x: fmt_cop(x, 2), "Beta": lambda x: fmt_num(x, 2),
                    "Score": lambda x: fmt_num(x, 1), "Ruptura": lambda x: "🚀 Sí" if x else "—",
                    "Monto prom. 20d (COP)": fmt_cop, "Ruedas sin negociar (20d)": lambda x: fmt_num(x, 0),
                    "Ilíquida": lambda x: "⚠️ Sí" if x else "—"})
        sec_filter = st.multiselect("Filtrar por sector", sorted(signals["Sector"].unique()), key="sig_sector")
        sig_view = signals[signals["Sector"].isin(sec_filter)] if sec_filter else signals
        show_df(sig_view.style.format(fmt))
        n_ill = int(signals["Ilíquida"].sum())
        if n_ill:
            st.caption(f"⚪ {n_ill} activo(s) marcados como ilíquidos (monto prom. < {fmt_cop(min_liq)} o "
                       f"≥ 8 ruedas sin negociar): {', '.join(signals.index[signals['Ilíquida']])}.")
        st.download_button("⬇️ Descargar señales (CSV)", signals.to_csv().encode("utf-8-sig"),
                           file_name=f"senales_{dt.date.today()}.csv", mime="text/csv")

        c1, c2 = st.columns(2)
        with c1:
            fr = signals["Alfa (anual)"].dropna().sort_values()
            if not fr.empty:
                fig = px.bar(x=fr.values * 100, y=fr.index, orientation="h",
                             color=np.where(fr.values >= 0, "Alfa +", "Alfa −"),
                             color_discrete_map={"Alfa +": "#2ca02c", "Alfa −": "#d62728"},
                             title="Ranking de alfa de Jensen vs COLCAP (anual, %)")
                fig.update_layout(showlegend=False, xaxis_title="%", yaxis_title="", height=420)
                show_chart(fig, key="alpha_rank")
        with c2:
            fig = px.scatter(signals.reset_index(), x="ROC 10", y="FR 20d vs COLCAP", text="Ticker",
                             size=signals["Score"].clip(lower=1).values, color="Señal",
                             title="Mapa momentum vs fuerza relativa")
            fig.update_traces(textposition="top center")
            fig.add_hline(y=0, line_color="gray")
            fig.add_vline(x=0, line_color="gray")
            fig.update_layout(height=420, xaxis_tickformat=".1%", yaxis_tickformat=".1%")
            show_chart(fig, key="mom_map")

        st.markdown("#### 🔍 Detalle técnico por activo")
        det = st.selectbox("Activo", list(signals.index), format_func=label, key="det_tk")
        d = data[det].iloc[-130:]
        up = d["High"].rolling(20).max().shift(1)
        dn = d["Low"].rolling(20).min().shift(1)
        roc10 = d["Close"] / d["Close"].shift(10) - 1
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.04)
        fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"],
                                     close=d["Close"], name=det), row=1, col=1)
        fig.add_trace(go.Scatter(x=d.index, y=up, name="Donchian sup. 20", line=dict(color="green", dash="dot")),
                      row=1, col=1)
        fig.add_trace(go.Scatter(x=d.index, y=dn, name="Donchian inf. 20", line=dict(color="red", dash="dot")),
                      row=1, col=1)
        fig.add_trace(go.Bar(x=d.index, y=roc10 * 100, name="ROC 10 (%)",
                             marker_color=np.where(roc10 >= 0, "#2ca02c", "#d62728")), row=2, col=1)
        fig.update_layout(height=520, xaxis_rangeslider_visible=False, title=label(det))
        show_chart(fig, key="detail_chart")


# =============================================================================
# 10. PESTAÑA 3 — BACKTESTING A 30 DÍAS
# =============================================================================
with tabs[2]:
    st.subheader("🧪 Backtesting de estrategias · ventanas móviles de 30 días (21 ruedas)")
    st.caption("Evalúa los últimos ~6 meses. En cada ventana la señal usa datos hasta t−1, se entra al cierre "
               "de t y se sale al cierre de t+21 (Donchian puede salir antes con el mínimo de 10 ruedas). "
               f"Se cobran {fmt_cop(COMMISSION, 2)} por cada orden. Capital por ventana: {fmt_cop(INITIAL_CAPITAL)}.")
    c1, c2, c3, c4 = st.columns(4)
    bt_top = c1.slider("Activos por estrategia (Top-N)", 1, 8, 3)
    bt_hold = c2.slider("Ruedas de tenencia", 10, 30, 21)
    bt_step = c3.slider("Paso entre ventanas (ruedas)", 1, 10, 5)
    bt_look = c4.selectbox("Periodo evaluado", {"6 meses": 126, "9 meses": 189, "12 meses": 252}.keys())
    look_days = {"6 meses": 126, "9 meses": 189, "12 meses": 252}[bt_look]

    if st.button("▶️ Ejecutar backtesting", type="primary"):
        if close.shape[1] < 2:
            st.error("Se necesitan al menos 2 activos con datos.")
        else:
            with st.spinner("Corriendo ventanas móviles…"):
                st.session_state["bt_result"] = run_backtest(close, high, low, bench, bt_top, bt_hold,
                                                             bt_step, look_days)
    bt = st.session_state.get("bt_result")
    if bt is not None and not bt.empty:
        summ = summarize_backtest(bt)
        best = summ["Retorno medio"].drop(["B&H COLCAP", "B&H Equiponderado"], errors="ignore").idxmax()
        st.success(f"🏅 Mejor estrategia activa por retorno medio neto: **{best}** "
                   f"({fmt_pct(summ.loc[best, 'Retorno medio'])} por ventana, acierto "
                   f"{fmt_pct(summ.loc[best, 'Tasa de acierto (>0)'], 0)}). {len(bt)} ventanas evaluadas.")
        fmt = {c: fmt_pct for c in summ.columns if c not in ("Ratio media/desv.", "Órdenes prom.")}
        fmt.update({"Ratio media/desv.": lambda x: fmt_num(x, 2), "Órdenes prom.": lambda x: fmt_num(x, 1)})
        show_df(summ.style.format(fmt))
        strat_cols = [c for c in summ.index]
        long = bt.melt(id_vars=["Inicio"], value_vars=strat_cols, var_name="Estrategia", value_name="Retorno")
        cc1, cc2 = st.columns(2)
        with cc1:
            fig = px.line(long, x="Inicio", y="Retorno", color="Estrategia", markers=True,
                          title="Retorno neto por ventana (fecha de inicio)")
            fig.update_layout(yaxis_tickformat=".1%", height=400)
            show_chart(fig, key="bt_lines")
        with cc2:
            fig = px.box(long, x="Estrategia", y="Retorno", color="Estrategia", points="all",
                         title="Distribución de retornos por ventana")
            fig.update_layout(yaxis_tickformat=".1%", showlegend=False, height=400)
            show_chart(fig, key="bt_box")
        with st.expander("Ver detalle de ventanas"):
            show_df(bt.drop(columns=[c for c in bt.columns if c.startswith("_")]).style.format(
                {c: fmt_pct for c in strat_cols}), hide_index=True)
        st.caption("⚠️ Resultados históricos in-sample; no garantizan desempeño futuro. Ventanas solapadas "
                   "(paso < tenencia) no son independientes.")


# =============================================================================
# 11. PESTAÑA 4 — PORTAFOLIO ÓPTIMO (MONTE CARLO + BLACK-LITTERMAN)
# =============================================================================
def render_result(name: str, res: dict, ctx: dict):
    """Muestra pesos, capital por acción, métricas, gráficos y simulación a 20 ruedas."""
    w = res["weights"]
    met = res["metrics"]
    alloc, residual = allocate_capital(w, last_prices, ctx["capital"])

    st.markdown(f"### {name} · objetivo: {ctx['objective']}")
    k = st.columns(5)
    k[0].metric("Retorno esperado (modelo, anual)", fmt_pct(res["exp_ret"]))
    k[1].metric("Volatilidad (modelo, anual)", fmt_pct(res["exp_vol"]))
    k[2].metric("Sharpe (modelo)", fmt_num((res["exp_ret"] - ctx["rf"]) / res["exp_vol"], 2)
                if res["exp_vol"] > 0 else "—")
    k[3].metric("Retorno esperado 20 ruedas", fmt_pct((1 + res["exp_ret"]) ** (CONTEST_DAYS / TRADING_DAYS) - 1))
    k[4].metric("Efectivo residual", fmt_cop(residual))

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**💰 Capital distribuido por acción**")
        show_df(alloc.style.format({
            "Peso óptimo": fmt_pct, "Peso real": fmt_pct, "Capital objetivo": fmt_cop,
            "Precio": lambda x: fmt_cop(x, 2), "Acciones": "{:,.0f}", "Capital invertido": fmt_cop,
            "Comisión": lambda x: fmt_cop(x, 2), "Costo total": fmt_cop,
            "Comisión / posición": lambda x: fmt_pct(x, 3)}), hide_index=True)
        st.caption(f"Capital: {fmt_cop(ctx['capital'])} · {len(alloc)} órdenes de compra × {fmt_cop(COMMISSION, 2)} "
                   f"= {fmt_cop(len(alloc) * COMMISSION, 2)} · pesos < 0,5% se descartan.")
        small = alloc[alloc["Comisión / posición"] * 2 > exp_margin * be_threshold]
        if not small.empty:
            st.warning(f"Posiciones pequeñas donde la comisión ida y vuelta supera el umbral de break-even: "
                       f"{', '.join(small['Ticker'])}. Considera aumentar wmin o reducir activos.")
    with c2:
        fig = px.pie(alloc, names="Ticker", values="Capital invertido", hole=0.45, title="Distribución del capital")
        show_chart(fig, key=f"pie_{name}")

    c1, c2 = st.columns(2)
    ret_keys = ["Retorno anualizado", "Retorno acumulado (ventana)", "Sharpe", "Sortino", "Information Ratio",
                "Alfa de Jensen (anual)", "Treynor", "Calmar", "Omega (umbral 0)", "Retorno COLCAP (anual)"]
    risk_keys = ["Volatilidad anual", "Beta", "Tracking Error", "Máximo Drawdown", "VaR 95% diario (hist.)",
                 "CVaR 95% diario", "Desviación a la baja (anual)", "Correlación vs COLCAP", "R²"]
    ratio_like = {"Sharpe", "Sortino", "Information Ratio", "Calmar", "Omega (umbral 0)", "Beta",
                  "Correlación vs COLCAP", "R²"}

    def _tbl(keys):
        return pd.DataFrame({"Métrica": keys,
                             "Valor": [fmt_num(met.get(x), 3) if x in ratio_like else fmt_pct(met.get(x))
                                       for x in keys]})
    with c1:
        st.markdown("**📈 Métricas de rentabilidad** (histórico, pesos constantes)")
        show_df(_tbl(ret_keys), hide_index=True)
    with c2:
        st.markdown("**🛡️ Métricas de riesgo**")
        show_df(_tbl(risk_keys), hide_index=True)
        var20 = 1.645 * res["exp_vol"] * math.sqrt(CONTEST_DAYS / TRADING_DAYS) * ctx["capital"]
        st.caption(f"VaR paramétrico 95% a 20 ruedas sobre el capital: **{fmt_cop(var20)}**")

    # gráficos específicos del método
    if "sims" in res:
        sims = res["sims"]
        sample = sims.sample(min(len(sims), 6000), random_state=1)
        fig = px.scatter(sample, x="Volatilidad", y="Retorno", color="Sharpe", opacity=0.55,
                         color_continuous_scale="Viridis", title="Frontera eficiente (Monte Carlo)")
        for lab, ix, sym in [("Máx. Sharpe", sims["Sharpe"].idxmax(), "star"),
                             ("Máx. Sortino", sims["Sortino"].idxmax(), "diamond"),
                             ("Mín. Volatilidad", sims["Volatilidad"].idxmin(), "x")]:
            fig.add_trace(go.Scatter(x=[sims.loc[ix, "Volatilidad"]], y=[sims.loc[ix, "Retorno"]], mode="markers",
                                     marker=dict(symbol=sym, size=16, color="red", line=dict(width=1, color="black")),
                                     name=lab))
        a_mu, a_vol = res["mu_hist"], np.sqrt(np.diag(res["cov_hist"]))
        fig.add_trace(go.Scatter(x=a_vol, y=a_mu, mode="markers+text", text=res["assets"], name="Activos",
                                 textposition="top center", marker=dict(size=9, color="black")))
        fig.update_layout(xaxis_tickformat=".0%", yaxis_tickformat=".0%", height=480)
        show_chart(fig, key=f"frontier_{name}")
    if "bl_table" in res:
        st.markdown("**🧭 Black-Litterman: equilibrio vs. views vs. posterior** (retornos anuales)")
        show_df(res["bl_table"].style.format(fmt_pct))
        if res["views_used"]:
            st.caption("Views aplicados: " + " · ".join(res["views_used"]))
        else:
            st.caption("Sin views válidos: el posterior = equilibrio de mercado (π).")
        bt_ = res["bl_table"][["Prior equilibrio (π)", "Histórico", "Posterior BL (μ)"]]
        fig = px.bar(bt_.reset_index().melt(id_vars="index"), x="index", y="value", color="variable",
                     barmode="group", title="Retornos esperados por activo")
        fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", height=380)
        show_chart(fig, key=f"bl_bars_{name}")

    # Simulación Monte Carlo hacia adelante (horizonte concurso)
    st.markdown("**🔮 Simulación Monte Carlo del valor del portafolio (horizonte del concurso)**")
    s1, s2, s3 = st.columns(3)
    horizon = s1.slider("Ruedas", 5, 60, CONTEST_DAYS, key=f"hz_{name}")
    n_paths = s2.select_slider("Trayectorias", [1000, 2000, 5000, 10000], 5000, key=f"np_{name}")
    sim_m = s3.radio("Modelo", ["Bootstrap histórico", "Normal multivariada (μ, Σ del modelo)"],
                     key=f"sm_{name}")
    wv = w.reindex(res["assets"]).fillna(0).values
    paths, final = simulate_forward(res["rets"], wv, ctx["capital"], horizon, n_paths, sim_m,
                                    res["mu_model"], res["cov_model"])
    q = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    x = np.arange(1, horizon + 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=q[4], line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=q[0], fill="tonexty", line=dict(width=0), name="P5–P95",
                             fillcolor="rgba(31,119,180,0.15)"))
    fig.add_trace(go.Scatter(x=x, y=q[3], line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=q[1], fill="tonexty", line=dict(width=0), name="P25–P75",
                             fillcolor="rgba(31,119,180,0.35)"))
    fig.add_trace(go.Scatter(x=x, y=q[2], name="Mediana", line=dict(color="#1f77b4")))
    fig.add_hline(y=ctx["capital"], line_dash="dash", line_color="gray")
    fig.update_layout(xaxis_title="Rueda", yaxis_title="COP", height=380)
    show_chart(fig, key=f"fan_{name}")
    pnl = final - ctx["capital"]
    v95 = -np.percentile(pnl, 5)
    m = st.columns(5)
    m[0].metric("PnL esperado (neto)", fmt_cop(pnl.mean()))
    m[1].metric("PnL mediano", fmt_cop(np.median(pnl)))
    m[2].metric("Prob. de pérdida", fmt_pct((pnl < 0).mean(), 1))
    m[3].metric("VaR 95%", fmt_cop(v95))
    m[4].metric("CVaR 95%", fmt_cop(-pnl[pnl <= -v95].mean()))

    # Ejecutar en el simulador
    with st.expander("🚀 Ejecutar este portafolio en el simulador"):
        need = alloc["Costo total"].sum()
        st.write(f"Costo total (incl. comisiones): **{fmt_cop(need, 2)}** · Efectivo disponible: "
                 f"**{fmt_cop(st.session_state['cash'], 2)}**")
        ok_chk = st.checkbox("Confirmo enviar estas órdenes de compra al simulador", key=f"conf_{name}")
        if st.button("Enviar órdenes", key=f"exec_{name}", disabled=not ok_chk):
            if need > st.session_state["cash"] + 1e-6:
                st.error("Efectivo insuficiente. Reduce el capital del optimizador.")
            else:
                msgs = []
                for _, row in alloc[alloc["Acciones"] > 0].iterrows():
                    ok, msg = execute_order(row["Ticker"], "COMPRA", int(row["Acciones"]), float(row["Precio"]),
                                            f"Portafolio {name}")
                    msgs.append(("✅ " if ok else "❌ ") + msg)
                flash("success", "Órdenes enviadas:\n\n" + "\n\n".join(msgs))
                rerun()


with tabs[3]:
    st.subheader("🎯 Constructor de Portafolio Óptimo")
    st.caption("Selecciona activos manualmente o deja que el ranking cuantitativo elija el Top-N. "
               "Optimiza por Monte Carlo (frontera eficiente) o Black-Litterman (equilibrio + tus supuestos).")
    available = [t for t in close.columns if close[t].dropna().shape[0] >= 60]
    if len(available) < 2:
        st.warning("Se necesitan al menos 2 activos con ≥ 60 ruedas de historia.")
    else:
        c1, c2, c3 = st.columns(3)
        sel_mode = c1.radio("Selección de activos", ["Automática (Top-N score)", "Manual"])
        # El Top-N automático excluye activos ilíquidos (siguen disponibles en modo Manual)
        ranked = [t for t in signals.index if t in available and not signals.loc[t, "Ilíquida"]] \
            if not signals.empty else available
        if len(ranked) < 2:
            ranked = available
        if sel_mode.startswith("Auto"):
            top_n = c1.slider("Top-N", 2, min(12, len(ranked)), min(5, len(ranked))) if len(ranked) > 2 else 2
            assets = ranked[:top_n]
            c1.caption("Seleccionados: " + ", ".join(assets))
        else:
            assets = c1.multiselect("Activos", available, default=ranked[:5], format_func=label)
        method = c2.radio("Método", ["Monte Carlo", "Black-Litterman", "Comparar ambos"])
        objective = c2.selectbox("Objetivo", ["Máximo Sharpe", "Máximo Sortino", "Mínima volatilidad",
                                              "Máxima utilidad (μ − δ/2·σ²)"])
        look_map = {"6 meses": 126, "1 año": 252, "2 años": 490}
        look = look_map[c3.selectbox("Ventana histórica", list(look_map), index=1)]
        capital = c3.number_input("Capital a invertir (COP)", 0.0, 1e10,
                                  float(max(st.session_state["cash"], 0)), 1_000_000.0,
                                  help="Por defecto, el efectivo disponible del simulador.")

        with st.expander("⚖️ Restricciones y simulación", expanded=False):
            r1, r2, r3 = st.columns(3)
            wmin = r1.slider("Peso mínimo por activo", 0.0, 0.2, 0.0, 0.01)
            wmax = r2.slider("Peso máximo por activo", 0.1, 1.0, 0.40, 0.05)
            n_sims = r3.select_slider("Simulaciones Monte Carlo", [2000, 5000, 10000, 20000, 50000], 10000)

        bl_on = method != "Monte Carlo"
        views_df = None
        if bl_on and len(assets) >= 2:
            with st.expander("🧭 Parámetros Black-Litterman y views (supuestos de mercado)", expanded=True):
                p1, p2, p3, p4 = st.columns(4)
                tau = p1.number_input("τ (incertidumbre del prior)", 0.01, 1.0, 0.05, 0.01)
                auto_delta = p2.checkbox("Estimar δ con el COLCAP", value=False)
                delta_in = p2.number_input("δ (aversión al riesgo)", 0.5, 10.0, 2.5, 0.1, disabled=auto_delta)
                prior_scheme = p3.radio("Pesos de equilibrio (w_mkt)",
                                        ["Equiponderado", "Inversa de volatilidad", "Manual"])
                shrink = p4.slider("Shrinkage de Σ hacia diagonal", 0.0, 1.0, 0.2, 0.05)
                manual_prior = None
                if prior_scheme == "Manual":
                    mp = st.data_editor(pd.DataFrame({"Activo": assets, "Peso (%)": [100 / len(assets)] * len(assets)}),
                                        hide_index=True, key=f"prior_{'_'.join(assets)}", disabled=["Activo"])
                    manual_prior = mp.set_index("Activo")["Peso (%)"].reindex(assets).fillna(0).values

                st.markdown("**Views** · *Absoluta*: 'X rendirá Y% anual' · *Relativa*: 'X superará a Z en Y% anual'. "
                            "La confianza (0–100%) controla Ω (método de Idzorek).")
                vkey = f"views_{st.session_state.get('views_ver', 0)}_{'_'.join(assets)}"
                if st.button("✨ Autogenerar views desde momentum (ROC 20d anualizado, atenuado 50%)"):
                    base = []
                    for a in [x for x in ranked if x in assets][:3]:
                        r20 = signals.loc[a, "ROC 20"] if a in signals.index else 0.0
                        ann = float(np.clip(((1 + r20) ** (TRADING_DAYS / 20) - 1) * 0.5, -0.5, 0.8))
                        base.append({"Tipo": "Absoluta", "Activo": a, "Vs. activo": "",
                                     "Retorno anual esperado (%)": round(ann * 100, 1), "Confianza (%)": 30.0})
                    st.session_state["views_seed"] = base
                    st.session_state["views_ver"] = st.session_state.get("views_ver", 0) + 1
                    rerun()
                seed_rows = st.session_state.get("views_seed") or [
                    {"Tipo": "Absoluta", "Activo": assets[0], "Vs. activo": "",
                     "Retorno anual esperado (%)": 15.0, "Confianza (%)": 50.0}]
                seed_rows = [r for r in seed_rows if r["Activo"] in assets] or [
                    {"Tipo": "Absoluta", "Activo": assets[0], "Vs. activo": "",
                     "Retorno anual esperado (%)": 15.0, "Confianza (%)": 50.0}]
                views_df = st.data_editor(
                    pd.DataFrame(seed_rows), num_rows="dynamic", hide_index=True, key=vkey,
                    column_config={
                        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Absoluta", "Relativa"], required=True),
                        "Activo": st.column_config.SelectboxColumn("Activo", options=assets, required=True),
                        "Vs. activo": st.column_config.SelectboxColumn("Vs. activo", options=[""] + assets),
                        "Retorno anual esperado (%)": st.column_config.NumberColumn(min_value=-100.0, max_value=300.0,
                                                                                   step=0.5, format="%.1f"),
                        "Confianza (%)": st.column_config.NumberColumn(min_value=1.0, max_value=99.0, step=1.0,
                                                                      format="%.0f"),
                    })

        if st.button("🚀 Calcular portafolio óptimo", type="primary"):
            if len(assets) < 2:
                st.error("Selecciona al menos 2 activos.")
            elif wmax * len(assets) < 1 - 1e-9 or wmin * len(assets) > 1 + 1e-9:
                st.error("Restricciones infactibles: verifica que N·wmin ≤ 1 ≤ N·wmax.")
            else:
                with st.spinner("Optimizando…"):
                    pxs = close[assets].iloc[-(look + 1):]
                    rets = pct(pxs).iloc[1:].dropna(how="any")
                    if len(rets) < 40:
                        st.error("Muy pocas observaciones comunes entre los activos seleccionados.")
                    else:
                        bench_ret = pct(bench.reindex(pxs.index).ffill()).reindex(rets.index) \
                            if bench is not None else None
                        mu_h = rets.mean().values * TRADING_DAYS
                        cov_h = rets.cov().values * TRADING_DAYS
                        results = {}

                        def _finish(w_arr, mu_m, cov_m, extra):
                            w_s = pd.Series(w_arr, index=assets)
                            out = {"weights": w_s, "assets": assets, "rets": rets, "mu_model": mu_m,
                                   "cov_model": cov_m, "mu_hist": mu_h, "cov_hist": cov_h,
                                   "exp_ret": float(w_arr @ mu_m),
                                   "exp_vol": math.sqrt(max(float(w_arr @ cov_m @ w_arr), 0)),
                                   "metrics": compute_metrics(pd.Series(rets.values @ w_arr, index=rets.index),
                                                              bench_ret, rf_annual)}
                            out.update(extra)
                            return out

                        if method in ("Monte Carlo", "Comparar ambos"):
                            sims, W = monte_carlo_portfolios(rets, rf_annual, n_sims, wmin, wmax)
                            if sims is None:
                                st.error("Ninguna simulación cumplió las restricciones.")
                            else:
                                if objective == "Mínima volatilidad":
                                    ix = int(sims["Volatilidad"].idxmin())
                                elif objective == "Máximo Sortino":
                                    ix = int(sims["Sortino"].idxmax())
                                elif objective.startswith("Máxima utilidad"):
                                    ix = int((sims["Retorno"] - 2.5 / 2 * sims["Volatilidad"] ** 2).idxmax())
                                else:
                                    ix = int(sims["Sharpe"].idxmax())
                                results["Monte Carlo"] = _finish(W[ix], mu_h, cov_h, {"sims": sims})

                        if method in ("Black-Litterman", "Comparar ambos"):
                            cov_s = (1 - shrink) * cov_h + shrink * np.diag(np.diag(cov_h))
                            if prior_scheme == "Inversa de volatilidad":
                                iv = 1 / np.sqrt(np.diag(cov_s))
                                w_prior = iv / iv.sum()
                            elif prior_scheme == "Manual" and manual_prior is not None and manual_prior.sum() > 0:
                                w_prior = manual_prior / manual_prior.sum()
                            else:
                                w_prior = np.full(len(assets), 1 / len(assets))
                            delta = delta_in
                            if auto_delta and bench_ret is not None and bench_ret.dropna().var() > 0:
                                bm = bench_ret.dropna()
                                delta = float(np.clip((bm.mean() * TRADING_DAYS - rf_annual) /
                                                      (bm.var() * TRADING_DAYS), 0.5, 6.0))
                            P, Q, C, used = parse_views(views_df, assets)
                            pi, cov_bl, mu_bl = black_litterman(cov_s, w_prior, delta, tau, P, Q, C)
                            scen = (rets - rets.mean()).values + mu_bl / TRADING_DAYS
                            w_bl = optimize_weights(mu_bl, cov_bl, rf_annual, objective, wmin, wmax, scen, delta)
                            tbl = pd.DataFrame({"Prior equilibrio (π)": pi, "Histórico": mu_h,
                                                "Posterior BL (μ)": mu_bl, "Peso equilibrio": w_prior,
                                                "Peso óptimo BL": w_bl}, index=assets)
                            results["Black-Litterman"] = _finish(w_bl, mu_bl, cov_bl,
                                                                 {"bl_table": tbl, "views_used": used,
                                                                  "delta": delta})
                        st.session_state["opt"] = {"results": results, "ctx": {
                            "capital": capital, "objective": objective, "rf": rf_annual, "look": look,
                            "n_obs": len(rets)}}

        opt = st.session_state.get("opt")
        if opt and opt["results"]:
            ctx = opt["ctx"]
            st.caption(f"Calculado con {ctx['n_obs']} ruedas comunes · rf = {fmt_pct(ctx['rf'])} · "
                       f"capital {fmt_cop(ctx['capital'])}. Métricas históricas = in-sample con pesos constantes.")
            res_all = opt["results"]
            if len(res_all) == 2:
                st.markdown("### ⚔️ Comparación Monte Carlo vs Black-Litterman")
                comp_w = pd.DataFrame({k2: v["weights"] for k2, v in res_all.items()})
                keys = ["Retorno anualizado", "Volatilidad anual", "Sharpe", "Sortino", "Information Ratio",
                        "Alfa de Jensen (anual)", "Beta", "Tracking Error", "Máximo Drawdown", "CVaR 95% diario"]
                comp_m = pd.DataFrame({k2: [v["metrics"].get(x) for x in keys] for k2, v in res_all.items()},
                                      index=keys)
                cc1, cc2 = st.columns(2)
                with cc1:
                    show_df(comp_w.style.format(fmt_pct))
                with cc2:
                    show_df(comp_m.style.format(lambda x: fmt_num(x, 3)))
                fig = px.bar(comp_w.reset_index().melt(id_vars="index"), x="index", y="value", color="variable",
                             barmode="group", title="Pesos por método")
                fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", height=360)
                show_chart(fig, key="cmp_weights")
            sub = st.tabs(list(res_all)) if len(res_all) > 1 else None
            for i, (nm, res) in enumerate(res_all.items()):
                if sub is not None:
                    with sub[i]:
                        render_result(nm, res, ctx)
                else:
                    render_result(nm, res, ctx)


# =============================================================================
# 12. PESTAÑA 5 — REFERENCIAS MACRO (SOLO LECTURA)
# =============================================================================
with tabs[4]:
    st.subheader("🌐 Referencias macro (no negociables)")
    if not macro:
        st.warning("No se pudieron descargar las referencias macro.")
    else:
        rows = []
        for nm, (tk_, df) in macro.items():
            c = df["Close"]

            def ch(n_):
                return c.iloc[-1] / c.iloc[-1 - n_] - 1 if len(c) > n_ else np.nan
            rows.append({"Referencia": nm, "Ticker": tk_, "Último": c.iloc[-1], "Fecha": c.index[-1].date(),
                         "1 día": ch(1), "5 días": ch(5), "20 días": ch(20), "60 días": ch(60)})
        mt = pd.DataFrame(rows).set_index("Referencia")
        show_df(mt.style.format({"Último": lambda x: fmt_num(x, 2), "1 día": fmt_pct, "5 días": fmt_pct,
                                 "20 días": fmt_pct, "60 días": fmt_pct}))
        per = {"1 mes": 21, "3 meses": 63, "6 meses": 126, "1 año": 252}
        pk = st.radio("Periodo", list(per), horizontal=True, index=2)
        norm = pd.DataFrame({nm: df["Close"] for nm, (_, df) in macro.items()}).ffill().iloc[-per[pk]:]
        norm = 100 * norm / norm.bfill().iloc[0]
        fig = px.line(norm, title="Referencias macro (base 100)")
        fig.update_layout(yaxis_title="Base 100", height=420)
        show_chart(fig, key="macro_norm")

        if not close.empty:
            st.markdown("**Sensibilidad del universo a factores macro** (correlación de rendimientos diarios, 120 ruedas)")
            mac_r = pct(pd.DataFrame({nm: df["Close"] for nm, (_, df) in macro.items()})).iloc[-121:]
            uni_r = pct(close).iloc[-121:]
            joined = pd.concat([uni_r, mac_r], axis=1, sort=True).dropna(how="all")
            corr = joined.corr().loc[uni_r.columns, mac_r.columns]
            fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
            fig.update_layout(height=max(320, 26 * len(corr)))
            show_chart(fig, key="macro_corr")


# =============================================================================
# 13. PESTAÑA 6 — BITÁCORA (JOURNALING DIARIO EN MARKDOWN)
# =============================================================================
with tabs[5]:
    st.subheader("📓 Bitácora diaria de trading")
    today = dt.date.today().isoformat()
    jday = st.date_input("Fecha de la entrada", dt.date.today()).isoformat()
    notes = st.session_state["journal"].get(jday, {})
    j1, j2 = st.columns(2)
    plan = j1.text_area("🎯 Plan / tesis del día", notes.get("plan", ""), height=110)
    exec_ = j1.text_area("⚙️ Ejecución (¿seguí el plan?)", notes.get("exec", ""), height=110)
    errors = j1.text_area("❌ Errores", notes.get("errors", ""), height=90)
    lessons = j2.text_area("💡 Lecciones", notes.get("lessons", ""), height=110)
    tomorrow = j2.text_area("📅 Plan para mañana", notes.get("tomorrow", ""), height=110)
    emo = j2.select_slider("🧠 Estado emocional", ["😫 1", "😟 2", "😐 3", "🙂 4", "😎 5"], notes.get("emo", "😐 3"))
    disc = j2.slider("📏 Disciplina (1–10)", 1, 10, int(notes.get("disc", 7)))
    if st.button("💾 Guardar notas del día"):
        st.session_state["journal"][jday] = {"plan": plan, "exec": exec_, "errors": errors, "lessons": lessons,
                                             "tomorrow": tomorrow, "emo": emo, "disc": disc}
        save_state()
        st.success("Notas guardadas.")

    # Entrada autogenerada con datos reales del simulador
    snap_j = portfolio_snapshot(last_prices)
    tx_all = pd.DataFrame(st.session_state["transactions"])
    tx_day = tx_all[tx_all["Fecha"].str.startswith(jday)] if not tx_all.empty else tx_all
    log = st.session_state["equity_log"]
    prev_days = sorted(d_ for d_ in log if d_ < jday)
    prev_eq = log[prev_days[-1]] if prev_days else INITIAL_CAPITAL
    day_eq = log.get(jday, snap_j["equity"])
    jd = dt.date.fromisoformat(jday)
    n_day = int(np.busday_count(start_date, jd + dt.timedelta(days=1)))

    md = [f"# 📓 Bitácora · Día {n_day}/{CONTEST_DAYS} · {jday}", "",
          "## 1. Resumen del portafolio", "| Métrica | Valor |", "|---|---|",
          f"| Patrimonio | {fmt_cop(day_eq)} |", f"| PnL del día | {fmt_cop(day_eq - prev_eq)} "
          f"({fmt_pct(day_eq / prev_eq - 1)}) |",
          f"| PnL acumulado neto | {fmt_cop(day_eq - INITIAL_CAPITAL)} ({fmt_pct(day_eq / INITIAL_CAPITAL - 1)}) |",
          f"| Efectivo | {fmt_cop(snap_j['cash'])} |", f"| Comisiones acumuladas | {fmt_cop(snap_j['comm_paid'], 2)} |",
          "", "## 2. Operaciones del día"]
    if tx_day is None or tx_day.empty:
        md.append("_Sin operaciones._")
    else:
        md += ["| Hora | Ticker | Op. | Cant. | Precio | Comisión | Total neto | PnL realiz. | Nota |",
               "|---|---|---|---|---|---|---|---|---|"]
        for _, r in tx_day.iterrows():
            md.append(f"| {r['Fecha'][11:16]} | {r['Ticker']} | {r['Operación']} | {r['Cantidad']:,} | "
                      f"{fmt_cop(r['Precio Ejecutado'], 2)} | {fmt_cop(r['Comisión'], 2)} | "
                      f"{fmt_cop(r['Total Neto'], 2)} | {fmt_cop(r['PnL Realizado'])} | {r.get('Nota', '')} |")
    md += ["", "## 3. Posiciones al cierre"]
    if snap_j["positions"].empty:
        md.append("_100% efectivo._")
    else:
        md += ["| Ticker | Cant. | Costo prom. | Precio | PnL no realiz. | Peso |", "|---|---|---|---|---|---|"]
        for _, r in snap_j["positions"].iterrows():
            md.append(f"| {r['Ticker']} | {r['Cantidad']:,} | {fmt_cop(r['Costo Prom. (c/comisión)'], 2)} | "
                      f"{fmt_cop(r['Último Precio'], 2)} | {fmt_cop(r['PnL No Realizado'])} | {fmt_pct(r['Peso %'])} |")
    md += ["", "## 4. Contexto macro"]
    for nm, (tk_, df) in macro.items():
        c = df["Close"]
        if len(c) > 1:
            md.append(f"- **{nm}**: {fmt_num(c.iloc[-1], 2)} ({fmt_pct(c.iloc[-1] / c.iloc[-2] - 1)} d/d)")
    md += ["", "## 5. Top 5 señales cuantitativas"]
    if not signals.empty:
        for t, r in signals.head(5).iterrows():
            md.append(f"- {t}: {r['Señal']} · Score {r['Score']:.1f} · ROC10 {fmt_pct(r['ROC 10'])} · "
                      f"FR {fmt_pct(r['FR 20d vs COLCAP'])}")
    md += ["", "## 6. Reflexión", f"**Plan / tesis:** {plan or '—'}", "", f"**Ejecución:** {exec_ or '—'}", "",
           f"**Errores:** {errors or '—'}", "", f"**Lecciones:** {lessons or '—'}", "",
           f"**Plan para mañana:** {tomorrow or '—'}", "",
           f"**Estado emocional:** {emo} · **Disciplina:** {disc}/10"]
    md_txt = "\n".join(md)
    with st.expander("👀 Vista previa de la entrada (Markdown)", expanded=True):
        st.markdown(md_txt)
    st.download_button("⬇️ Descargar entrada del día (.md)", md_txt.encode("utf-8"),
                       file_name=f"bitacora_{jday}.md", mime="text/markdown")

st.caption("⚠️ Herramienta educativa de simulación. Datos de Yahoo Finance (pueden tener retraso o huecos); "
           "los tickers MGC sin cotización en Yahoo se aproximan con subyacente USA × USD/COP. "
           "No constituye recomendación de inversión.")

"""
TÉRRET MERCH — Plataforma de tiendas personalizadas por equipo
Streamlit + Google Sheets + Shopify Draft Orders
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import requests
import urllib.parse
import uuid
from datetime import datetime
import json

st.set_page_config(
    page_title="Térret Merch",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CONSTANTES ───────────────────────────────────────────────────────────────
SPREADSHEET_ID  = st.secrets.get("MERCH_SPREADSHEET_ID", "")
TIENDA_URL      = st.secrets.get("TIENDA_URL", "terret-col.myshopify.com")
SHOPIFY_TOKEN   = st.secrets.get("SHOPIFY_ACCESS_TOKEN", "")
ADMIN_PASSWORD  = st.secrets.get("MERCH_ADMIN_PASSWORD", "terret2024")
API_VERSION     = "2024-01"

HOJA_EQUIPOS   = "Equipos"
HOJA_PRODUCTOS = "Productos"
HOJA_PEDIDOS   = "Pedidos"

# ─── ESTILOS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #0A0A0A !important;
    color: #F5F0E8 !important;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stAppViewContainer"] > .main { background: #0A0A0A; }
[data-testid="stHeader"] { background: #0A0A0A !important; border-bottom: 1px solid #222; }
[data-testid="stSidebar"] { background: #111 !important; }

[data-testid="stMetric"] {
    background: #111;
    border: 1px solid #222;
    border-radius: 6px;
    padding: 12px 16px;
}
[data-testid="stMetricValue"] {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 2rem !important;
    color: #F5F0E8 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 9px !important;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #666 !important;
}

.stButton > button {
    background: #F5F0E8 !important;
    color: #0A0A0A !important;
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 14px !important;
    letter-spacing: 2px !important;
    border: none !important;
    border-radius: 3px !important;
    padding: 10px 20px !important;
    width: 100%;
}
.stButton > button:hover { opacity: 0.85 !important; }

.stTextInput input, .stNumberInput input, .stSelectbox > div > div {
    background: #111 !important;
    border: 1px solid #333 !important;
    color: #F5F0E8 !important;
    border-radius: 3px !important;
}

/* Radio buttons */
[data-testid="stRadio"] label { color: #F5F0E8 !important; }
[data-testid="stRadio"] p { color: #F5F0E8 !important; }

hr { border-color: #222 !important; }

/* Ocultar el menú de Streamlit */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─── SHEETS ───────────────────────────────────────────────────────────────────
@st.cache_resource(ttl=300)
def conectar_sheets():
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error Sheets: {e}")
        return None


def get_ws(client, nombre, headers=None):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            return sh.worksheet(nombre)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=nombre, rows=1000, cols=30)
            if headers:
                ws.append_row(headers)
                ws.format("1:1", {
                    "backgroundColor": {"red": 0, "green": 0, "blue": 0},
                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                   "bold": True}
                })
            return ws
    except Exception as e:
        st.error(f"Error hoja '{nombre}': {e}")
        return None


@st.cache_data(ttl=60)
def leer_equipos(_client):
    ws = get_ws(_client, HOJA_EQUIPOS,
                ["ID", "Nombre", "Codigo", "Color_Primario", "Color_Secundario",
                 "Logo_URL", "Fecha_Corte", "Descripcion", "Activo"])
    if not ws: return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID","Nombre","Codigo","Color_Primario","Color_Secundario",
                 "Logo_URL","Fecha_Corte","Descripcion","Activo"])


@st.cache_data(ttl=60)
def leer_productos(_client):
    ws = get_ws(_client, HOJA_PRODUCTOS,
                ["ID", "Equipo_ID", "Nombre", "Descripcion", "Precio",
                 "Foto_URL", "Tallas", "Colores", "Stock_Info", "Activo"])
    if not ws: return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID","Equipo_ID","Nombre","Descripcion","Precio",
                 "Foto_URL","Tallas","Colores","Stock_Info","Activo"])


@st.cache_data(ttl=30)
def leer_pedidos(_client):
    ws = get_ws(_client, HOJA_PEDIDOS,
                ["ID", "Fecha", "Equipo_ID", "Equipo_Nombre", "Jugador_Nombre",
                 "Jugador_Email", "Productos_JSON", "Total", "Shopify_Order_ID",
                 "Shopify_Draft_ID", "Estado", "Notas"])
    if not ws: return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID","Fecha","Equipo_ID","Equipo_Nombre","Jugador_Nombre",
                 "Jugador_Email","Productos_JSON","Total","Shopify_Order_ID",
                 "Shopify_Draft_ID","Estado","Notas"])


def guardar_equipo(client, equipo):
    ws = get_ws(client, HOJA_EQUIPOS)
    if not ws: return False
    try:
        ws.append_row([
            equipo["id"], equipo["nombre"], equipo["codigo"],
            equipo["color_primario"], equipo["color_secundario"],
            equipo["logo_url"], equipo["fecha_corte"],
            equipo["descripcion"], "SI"
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando equipo: {e}")
        return False


def guardar_producto(client, producto):
    ws = get_ws(client, HOJA_PRODUCTOS)
    if not ws: return False
    try:
        ws.append_row([
            producto["id"], producto["equipo_id"], producto["nombre"],
            producto["descripcion"], producto["precio"],
            producto["foto_url"], producto["tallas"],
            producto["colores"], producto.get("stock_info", ""),
            "SI"
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando producto: {e}")
        return False


def guardar_pedido(client, pedido):
    ws = get_ws(client, HOJA_PEDIDOS)
    if not ws: return False
    try:
        ws.append_row([
            pedido["id"], pedido["fecha"], pedido["equipo_id"],
            pedido["equipo_nombre"], pedido["jugador_nombre"],
            pedido["jugador_email"], json.dumps(pedido["productos"]),
            pedido["total"], pedido.get("shopify_order_id", ""),
            pedido.get("shopify_draft_id", ""), "PENDIENTE",
            pedido.get("notas", "")
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando pedido: {e}")
        return False


def actualizar_pedido_estado(client, pedido_id, order_id, estado="PAGADO"):
    ws = get_ws(client, HOJA_PEDIDOS)
    if not ws: return False
    try:
        cell = ws.find(pedido_id)
        if cell:
            ws.update_cell(cell.row, 9, order_id)   # Shopify_Order_ID
            ws.update_cell(cell.row, 11, estado)     # Estado
        st.cache_data.clear()
        return True
    except:
        return False


# ─── SHOPIFY DRAFT ORDERS ─────────────────────────────────────────────────────
def crear_draft_order(items, cliente_email, cliente_nombre, equipo_nombre, pedido_id):
    """
    Crea una Draft Order en Shopify con line items personalizados.
    No requiere que los productos existan en Shopify.
    """
    if not SHOPIFY_TOKEN:
        return None, "No hay token de Shopify configurado."

    url = f"https://{TIENDA_URL}/admin/api/{API_VERSION}/draft_orders.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }

    line_items = []
    for item in items:
        line_items.append({
            "title":    item["nombre"],
            "price":    str(item["precio"]),
            "quantity": item["cantidad"],
            "requires_shipping": True,
            "taxable": True,
            "properties": [
                {"name": "Talla",  "value": item.get("talla", "")},
                {"name": "Color",  "value": item.get("color", "")},
                {"name": "Equipo", "value": equipo_nombre},
            ],
        })

    payload = {
        "draft_order": {
            "line_items": line_items,
            "customer": {
                "email": cliente_email,
                "first_name": cliente_nombre.split()[0] if cliente_nombre else "",
                "last_name":  " ".join(cliente_nombre.split()[1:]) if len(cliente_nombre.split()) > 1 else "",
            },
            "use_customer_default_address": False,
            "note": f"Pedido {pedido_id} — {equipo_nombre}",
            "tags": f"merch,{equipo_nombre.lower().replace(' ','-')}",
            "send_receipt": False,
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 201:
            draft = resp.json()["draft_order"]
            return draft, None
        else:
            return None, f"Error Shopify: {resp.text}"
    except Exception as e:
        return None, str(e)


def completar_draft_order(draft_id):
    """Convierte la draft order a orden real (para cuando el pago se confirma)."""
    url = f"https://{TIENDA_URL}/admin/api/{API_VERSION}/draft_orders/{draft_id}/complete.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    try:
        resp = requests.put(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()["draft_order"]["order_id"]
        return None
    except:
        return None


# ─── HELPERS UI ───────────────────────────────────────────────────────────────
def seccion(titulo, subtitulo=""):
    sub = f"<div style='font-size:11px;color:#666;letter-spacing:1px;margin-top:2px;'>{subtitulo}</div>" if subtitulo else ""
    st.markdown(
        f"<div style='margin:32px 0 20px 0;padding-bottom:12px;border-bottom:1px solid #222;'>"
        f"<div style='font-family:Bebas Neue,sans-serif;font-size:22px;letter-spacing:3px;"
        f"color:#F5F0E8;'>{titulo}</div>{sub}</div>",
        unsafe_allow_html=True,
    )


def badge(texto, color="#F5F0E8", bg="#222"):
    return (f"<span style='background:{bg};color:{color};font-size:10px;"
            f"letter-spacing:1.5px;text-transform:uppercase;padding:3px 8px;"
            f"border-radius:2px;font-family:DM Mono,monospace;'>{texto}</span>")


def fmt_precio(v):
    return f"${v:,.0f}"


# ─── VISTA ADMIN ──────────────────────────────────────────────────────────────
def vista_admin(client):
    # Header admin
    st.markdown(
        "<div style='display:flex;align-items:center;gap:16px;margin-bottom:32px;'>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;letter-spacing:4px;'>⚡ TÉRRET MERCH</div>"
        "<div style='background:#333;color:#888;font-size:10px;letter-spacing:2px;"
        "padding:4px 10px;border-radius:2px;font-family:DM Mono,monospace;'>PANEL ADMIN</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3 = st.tabs(["📦 Equipos", "👕 Productos", "📋 Pedidos"])

    # ── TAB 1: EQUIPOS ────────────────────────────────────────────────────────
    with tab1:
        df_eq = leer_equipos(client)

        seccion("EQUIPOS", f"{len(df_eq)} equipos registrados")

        # Métricas
        if not df_eq.empty:
            activos = len(df_eq[df_eq["Activo"] == "SI"]) if "Activo" in df_eq.columns else len(df_eq)
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Total equipos", len(df_eq))
            with c2: st.metric("Activos", activos)
            with c3: st.metric("Con corte próximo", "—")

        # Lista de equipos
        if not df_eq.empty:
            for _, eq in df_eq.iterrows():
                color = eq.get("Color_Primario", "#F5F0E8") or "#F5F0E8"
                st.markdown(
                    f"<div style='background:#111;border:1px solid #222;"
                    f"border-left:3px solid {color};border-radius:6px;"
                    f"padding:14px 18px;margin-bottom:8px;"
                    f"display:flex;align-items:center;justify-content:space-between;'>"
                    f"<div>"
                    f"<div style='font-weight:600;font-size:14px;'>{eq.get('Nombre','')}</div>"
                    f"<div style='font-size:11px;color:#666;margin-top:2px;'>"
                    f"Código: <span style='font-family:DM Mono,monospace;color:#F5F0E8;'>"
                    f"{eq.get('Codigo','')}</span>"
                    f" · Corte: {eq.get('Fecha_Corte','—')}</div>"
                    f"</div>"
                    f"<div style='font-size:10px;color:#666;font-family:DM Mono,monospace;'>"
                    f"ID: {eq.get('ID','')}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # Formulario nuevo equipo
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        with st.expander("➕ CREAR NUEVO EQUIPO", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                eq_nombre = st.text_input("Nombre del equipo *", key="eq_nombre",
                                           placeholder="Ej: Atlético Running Club")
                eq_codigo = st.text_input("Código de acceso *", key="eq_codigo",
                                           placeholder="Ej: ARC2024 (lo usan los jugadores)")
                eq_fecha  = st.text_input("Fecha de corte", key="eq_fecha",
                                           placeholder="Ej: 15/02/2025")
            with c2:
                eq_color1 = st.color_picker("Color primario", "#F5F0E8", key="eq_color1")
                eq_color2 = st.color_picker("Color secundario", "#0A0A0A", key="eq_color2")
                eq_logo   = st.text_input("URL del logo (Drive/Imgur)", key="eq_logo",
                                           placeholder="https://...")
            eq_desc = st.text_area("Descripción / mensaje para el equipo", key="eq_desc",
                                    placeholder="Ej: ¡Bienvenido al portal de merch oficial de ARC!")

            if st.button("CREAR EQUIPO", key="btn_crear_eq"):
                if not eq_nombre or not eq_codigo:
                    st.error("Nombre y código son obligatorios.")
                else:
                    nuevo = {
                        "id":               str(uuid.uuid4())[:8].upper(),
                        "nombre":           eq_nombre,
                        "codigo":           eq_codigo.upper().strip(),
                        "color_primario":   eq_color1,
                        "color_secundario": eq_color2,
                        "logo_url":         eq_logo,
                        "fecha_corte":      eq_fecha,
                        "descripcion":      eq_desc,
                    }
                    if guardar_equipo(client, nuevo):
                        st.success(f"✅ Equipo **{eq_nombre}** creado · Código: `{eq_codigo.upper()}`")
                        st.info(f"🔗 Link para el equipo: `?equipo={eq_codigo.upper()}`")

    # ── TAB 2: PRODUCTOS ──────────────────────────────────────────────────────
    with tab2:
        df_eq  = leer_equipos(client)
        df_pro = leer_productos(client)

        seccion("PRODUCTOS", f"{len(df_pro)} productos cargados")

        if not df_pro.empty and not df_eq.empty:
            # Filtro por equipo
            eq_nombres = ["Todos"] + df_eq["Nombre"].tolist()
            filtro_eq = st.selectbox("Filtrar por equipo:", eq_nombres, key="filtro_eq_prod")

            df_show = df_pro.copy()
            if filtro_eq != "Todos":
                eq_id = df_eq[df_eq["Nombre"] == filtro_eq]["ID"].iloc[0]
                df_show = df_pro[df_pro["Equipo_ID"] == eq_id]

            for _, p in df_show.iterrows():
                eq_row = df_eq[df_eq["ID"] == p.get("Equipo_ID","")]
                eq_nombre = eq_row["Nombre"].iloc[0] if not eq_row.empty else "—"
                st.markdown(
                    f"<div style='background:#111;border:1px solid #222;border-radius:6px;"
                    f"padding:12px 18px;margin-bottom:6px;"
                    f"display:flex;align-items:center;justify-content:space-between;'>"
                    f"<div>"
                    f"<div style='font-weight:600;'>{p.get('Nombre','')}</div>"
                    f"<div style='font-size:11px;color:#666;margin-top:2px;'>"
                    f"{eq_nombre} · Tallas: {p.get('Tallas','')} · Colores: {p.get('Colores','')}</div>"
                    f"</div>"
                    f"<div style='font-family:Bebas Neue,sans-serif;font-size:20px;color:#F5F0E8;'>"
                    f"{fmt_precio(float(p.get('Precio',0)))}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # Formulario nuevo producto
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        with st.expander("➕ AGREGAR PRODUCTO", expanded=False):
            if df_eq.empty:
                st.warning("Primero crea un equipo.")
            else:
                eq_opciones = {row["Nombre"]: row["ID"] for _, row in df_eq.iterrows()}

                c1, c2 = st.columns(2)
                with c1:
                    prod_equipo = st.selectbox("Equipo *", list(eq_opciones.keys()), key="prod_eq")
                    prod_nombre = st.text_input("Nombre del producto *", key="prod_nombre",
                                                 placeholder="Ej: Camiseta Running Pro")
                    prod_precio = st.number_input("Precio (COP) *", min_value=0,
                                                   step=1000, key="prod_precio")
                    prod_foto   = st.text_input("URL de la foto", key="prod_foto",
                                                 placeholder="https://drive.google.com/...")
                with c2:
                    prod_tallas = st.text_input("Tallas disponibles", key="prod_tallas",
                                                 placeholder="XS,S,M,L,XL,XXL")
                    prod_colores = st.text_input("Colores disponibles", key="prod_colores",
                                                  placeholder="Negro,Blanco,Gris")
                    prod_desc   = st.text_area("Descripción", key="prod_desc",
                                                placeholder="Materiales, detalles del diseño...")

                if st.button("AGREGAR PRODUCTO", key="btn_add_prod"):
                    if not prod_nombre or prod_precio <= 0:
                        st.error("Nombre y precio son obligatorios.")
                    else:
                        nuevo = {
                            "id":        str(uuid.uuid4())[:8].upper(),
                            "equipo_id": eq_opciones[prod_equipo],
                            "nombre":    prod_nombre,
                            "descripcion": prod_desc,
                            "precio":    prod_precio,
                            "foto_url":  prod_foto,
                            "tallas":    prod_tallas,
                            "colores":   prod_colores,
                        }
                        if guardar_producto(client, nuevo):
                            st.success(f"✅ Producto **{prod_nombre}** agregado a {prod_equipo}")

    # ── TAB 3: PEDIDOS ────────────────────────────────────────────────────────
    with tab3:
        df_eq  = leer_equipos(client)
        df_ped = leer_pedidos(client)

        seccion("PEDIDOS", f"{len(df_ped)} pedidos registrados")

        if df_ped.empty:
            st.info("Aún no hay pedidos registrados.")
        else:
            # Métricas
            pagados   = len(df_ped[df_ped["Estado"] == "PAGADO"]) if "Estado" in df_ped.columns else 0
            pendientes = len(df_ped[df_ped["Estado"] == "PENDIENTE"]) if "Estado" in df_ped.columns else 0
            total_cop  = df_ped["Total"].apply(lambda x: float(str(x).replace(",","")) if x else 0).sum()

            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Total pedidos", len(df_ped))
            with c2: st.metric("Pagados", pagados)
            with c3: st.metric("Pendientes", pendientes)
            with c4: st.metric("Valor total", fmt_precio(total_cop))

            # Filtros
            c1, c2 = st.columns(2)
            with c1:
                equipos_ped = ["Todos"] + df_ped["Equipo_Nombre"].dropna().unique().tolist()
                filtro_eq_p = st.selectbox("Filtrar por equipo:", equipos_ped, key="filtro_eq_ped")
            with c2:
                estados = ["Todos", "PENDIENTE", "PAGADO", "PRODUCCION", "ENVIADO"]
                filtro_est = st.selectbox("Estado:", estados, key="filtro_est_ped")

            df_show = df_ped.copy()
            if filtro_eq_p != "Todos":
                df_show = df_show[df_show["Equipo_Nombre"] == filtro_eq_p]
            if filtro_est != "Todos":
                df_show = df_show[df_show["Estado"] == filtro_est]

            # Tabla de pedidos
            for _, p in df_show.sort_values("Fecha", ascending=False).iterrows():
                estado = p.get("Estado", "PENDIENTE")
                color_estado = {
                    "PAGADO":     "#00C853",
                    "PENDIENTE":  "#FFB800",
                    "PRODUCCION": "#4488FF",
                    "ENVIADO":    "#2D6A4F",
                }.get(estado, "#666")

                # Parsear productos
                try:
                    prods = json.loads(p.get("Productos_JSON", "[]"))
                    prods_str = " · ".join([f"{pr['nombre']} ({pr.get('talla','')}/{pr.get('color','')}) x{pr['cantidad']}"
                                             for pr in prods])
                except:
                    prods_str = str(p.get("Productos_JSON", ""))

                st.markdown(
                    f"<div style='background:#111;border:1px solid #222;border-radius:6px;"
                    f"padding:14px 18px;margin-bottom:8px;'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;"
                    f"margin-bottom:8px;'>"
                    f"<div>"
                    f"<span style='font-weight:600;'>{p.get('Jugador_Nombre','—')}</span>"
                    f"<span style='color:#666;font-size:12px;margin-left:10px;'>"
                    f"{p.get('Jugador_Email','')}</span>"
                    f"</div>"
                    f"<div style='display:flex;gap:10px;align-items:center;'>"
                    f"<span style='font-family:Bebas Neue,sans-serif;font-size:18px;'>"
                    f"{fmt_precio(float(str(p.get('Total',0)).replace(',','')))}</span>"
                    f"<span style='background:{color_estado}22;color:{color_estado};"
                    f"font-size:9px;letter-spacing:1.5px;padding:3px 8px;border-radius:2px;"
                    f"font-family:DM Mono,monospace;'>{estado}</span>"
                    f"</div>"
                    f"</div>"
                    f"<div style='font-size:11px;color:#888;'>"
                    f"<b style='color:#666;'>Equipo:</b> {p.get('Equipo_Nombre','—')} · "
                    f"<b style='color:#666;'>Fecha:</b> {p.get('Fecha','—')} · "
                    f"<b style='color:#666;'>ID:</b> {p.get('ID','—')}"
                    f"</div>"
                    f"<div style='font-size:11px;color:#888;margin-top:6px;'>{prods_str}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # Exportar para producción
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            if st.button("📥 DESCARGAR REPORTE DE PRODUCCIÓN (CSV)", key="btn_export"):
                try:
                    df_export = df_show.copy()
                    csv = df_export.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "⬇️ Descargar CSV",
                        csv,
                        f"pedidos_terret_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv",
                        key="dl_csv",
                    )
                except Exception as e:
                    st.error(f"Error exportando: {e}")


# ─── VISTA TIENDA EQUIPO ──────────────────────────────────────────────────────
def vista_tienda(client, codigo_equipo):
    df_eq  = leer_equipos(client)
    df_pro = leer_productos(client)

    # Buscar equipo por código
    eq_row = df_eq[df_eq["Codigo"].str.upper() == codigo_equipo.upper()]
    if eq_row.empty:
        st.markdown(
            "<div style='max-width:480px;margin:120px auto;text-align:center;'>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;letter-spacing:3px;"
            "margin-bottom:12px;'>COLECCIÓN NO ENCONTRADA</div>"
            "<div style='color:#666;font-size:14px;'>El código de equipo no es válido.<br>"
            "Verifica con tu coach o con Térret.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    eq = eq_row.iloc[0]
    eq_id       = eq["ID"]
    eq_nombre   = eq["Nombre"]
    eq_desc     = eq.get("Descripcion", "")
    eq_color    = eq.get("Color_Primario", "#F5F0E8") or "#F5F0E8"
    eq_logo     = eq.get("Logo_URL", "")
    eq_corte    = eq.get("Fecha_Corte", "")

    # Productos del equipo
    productos = df_pro[(df_pro["Equipo_ID"] == eq_id) & (df_pro["Activo"] == "SI")]

    # ── Header tienda ──────────────────────────────────────────────────────────
    logo_html = f"<img src='{eq_logo}' style='height:48px;object-fit:contain;margin-right:16px;'>" if eq_logo else ""
    st.markdown(
        f"<div style='border-bottom:1px solid #222;padding:20px 0 20px 0;margin-bottom:32px;"
        f"display:flex;align-items:center;'>"
        f"{logo_html}"
        f"<div>"
        f"<div style='font-size:10px;color:#666;letter-spacing:3px;text-transform:uppercase;"
        f"font-family:DM Mono,monospace;margin-bottom:4px;'>Colección Exclusiva</div>"
        f"<div style='font-family:Bebas Neue,sans-serif;font-size:32px;letter-spacing:4px;"
        f"color:{eq_color};'>{eq_nombre.upper()}</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if eq_desc:
        st.markdown(
            f"<div style='color:#888;font-size:14px;margin-bottom:8px;'>{eq_desc}</div>",
            unsafe_allow_html=True,
        )

    if eq_corte:
        st.markdown(
            f"<div style='background:#1a1a00;border:1px solid #333300;border-radius:4px;"
            f"padding:10px 16px;margin-bottom:24px;font-size:12px;color:#FFB800;'>"
            f"⏰ Fecha límite de pedidos: <b>{eq_corte}</b></div>",
            unsafe_allow_html=True,
        )

    if productos.empty:
        st.markdown(
            "<div style='text-align:center;padding:60px;color:#666;'>"
            "No hay productos disponibles aún. Contacta a Térret.</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Carrito en session state ───────────────────────────────────────────────
    if "carrito" not in st.session_state:
        st.session_state.carrito = []

    # ── Grid de productos ──────────────────────────────────────────────────────
    seccion("PRODUCTOS DE LA COLECCIÓN", f"{len(productos)} prendas disponibles")

    cols = st.columns(3)
    for i, (_, prod) in enumerate(productos.iterrows()):
        with cols[i % 3]:
            foto = prod.get("Foto_URL", "")
            precio = float(prod.get("Precio", 0))
            tallas = [t.strip() for t in str(prod.get("Tallas","")).split(",") if t.strip()]
            colores = [c.strip() for c in str(prod.get("Colores","")).split(",") if c.strip()]

            # Card del producto
            img_html = (f"<img src='{foto}' style='width:100%;height:200px;"
                        f"object-fit:cover;border-radius:4px 4px 0 0;'>"
                        if foto else
                        f"<div style='width:100%;height:200px;background:#1a1a1a;"
                        f"border-radius:4px 4px 0 0;display:flex;align-items:center;"
                        f"justify-content:center;color:#333;font-size:32px;'>👕</div>")

            st.markdown(
                f"<div style='background:#111;border:1px solid #222;border-radius:6px;"
                f"margin-bottom:8px;overflow:hidden;'>"
                f"{img_html}"
                f"<div style='padding:14px;'>"
                f"<div style='font-weight:600;font-size:14px;margin-bottom:4px;'>"
                f"{prod.get('Nombre','')}</div>"
                f"<div style='font-size:12px;color:#666;margin-bottom:8px;'>"
                f"{prod.get('Descripcion','')[:80]}...</div>"
                f"<div style='font-family:Bebas Neue,sans-serif;font-size:22px;color:{eq_color};'>"
                f"{fmt_precio(precio)}</div>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            # Selector talla y color
            prod_key = f"prod_{prod['ID']}"
            if tallas:
                talla_sel = st.selectbox("Talla", tallas, key=f"talla_{prod_key}")
            else:
                talla_sel = ""

            if colores:
                color_sel = st.selectbox("Color", colores, key=f"color_{prod_key}")
            else:
                color_sel = ""

            cant = st.number_input("Cantidad", min_value=1, max_value=20,
                                    value=1, key=f"cant_{prod_key}")

            if st.button("AGREGAR AL CARRITO", key=f"add_{prod_key}"):
                st.session_state.carrito.append({
                    "prod_id":  prod["ID"],
                    "nombre":   prod["Nombre"],
                    "precio":   precio,
                    "talla":    talla_sel,
                    "color":    color_sel,
                    "cantidad": int(cant),
                })
                st.success(f"✅ {prod['Nombre']} agregado")

    # ── Carrito ────────────────────────────────────────────────────────────────
    if st.session_state.carrito:
        seccion("TU PEDIDO", "Revisa y confirma antes de pagar")

        total = 0
        for idx, item in enumerate(st.session_state.carrito):
            subtotal = item["precio"] * item["cantidad"]
            total += subtotal
            c1, c2, c3 = st.columns([4, 2, 1])
            with c1:
                st.markdown(
                    f"<div style='padding:10px 0;border-bottom:1px solid #1a1a1a;'>"
                    f"<div style='font-weight:500;'>{item['nombre']}</div>"
                    f"<div style='font-size:11px;color:#666;'>"
                    f"Talla: {item['talla']} · Color: {item['color']} · "
                    f"x{item['cantidad']}</div></div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f"<div style='padding:10px 0;text-align:right;"
                    f"font-family:Bebas Neue,sans-serif;font-size:18px;'>"
                    f"{fmt_precio(subtotal)}</div>",
                    unsafe_allow_html=True,
                )
            with c3:
                if st.button("✕", key=f"rm_{idx}"):
                    st.session_state.carrito.pop(idx)
                    st.rerun()

        st.markdown(
            f"<div style='background:#1a1a1a;border-radius:4px;padding:14px 18px;"
            f"display:flex;justify-content:space-between;align-items:center;"
            f"margin:12px 0 24px 0;'>"
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:16px;letter-spacing:2px;'>"
            f"TOTAL</div>"
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:28px;color:{eq_color};'>"
            f"{fmt_precio(total)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Datos del comprador
        seccion("TUS DATOS", "Para procesar tu pedido")
        c1, c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Nombre completo *", key="buyer_nombre",
                                    placeholder="Como quieres que aparezca en el pedido")
        with c2:
            email = st.text_input("Correo electrónico *", key="buyer_email",
                                   placeholder="Para enviarte la confirmación")

        notas = st.text_area("Notas adicionales", key="buyer_notas",
                              placeholder="Dirección de envío, instrucciones especiales...")

        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn1:
            if st.button("🛒 PROCEDER AL PAGO", key="btn_pagar"):
                if not nombre or not email:
                    st.error("Nombre y correo son obligatorios.")
                elif "@" not in email:
                    st.error("El correo no es válido.")
                else:
                    pedido_id = f"TM-{str(uuid.uuid4())[:6].upper()}"

                    with st.spinner("Creando tu orden..."):
                        draft, err = crear_draft_order(
                            items=st.session_state.carrito,
                            cliente_email=email,
                            cliente_nombre=nombre,
                            equipo_nombre=eq_nombre,
                            pedido_id=pedido_id,
                        )

                    if err or not draft:
                        st.error(f"Error creando la orden: {err}")
                    else:
                        # Guardar en Sheets
                        pedido_data = {
                            "id":              pedido_id,
                            "fecha":           datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "equipo_id":       eq_id,
                            "equipo_nombre":   eq_nombre,
                            "jugador_nombre":  nombre,
                            "jugador_email":   email,
                            "productos":       st.session_state.carrito,
                            "total":           total,
                            "shopify_draft_id": draft["id"],
                            "notas":           notas,
                        }
                        guardar_pedido(client, pedido_data)

                        # Redirigir al checkout de Shopify
                        checkout_url = draft.get("invoice_url", "")
                        if checkout_url:
                            st.session_state.carrito = []
                            st.markdown(
                                f"<div style='background:#0a1a0a;border:1px solid #1a3a1a;"
                                f"border-radius:6px;padding:20px;text-align:center;'>"
                                f"<div style='font-family:Bebas Neue,sans-serif;font-size:20px;"
                                f"color:#00C853;letter-spacing:2px;margin-bottom:8px;'>"
                                f"✅ PEDIDO REGISTRADO</div>"
                                f"<div style='color:#888;font-size:13px;margin-bottom:16px;'>"
                                f"Tu pedido <b style='color:#F5F0E8;'>{pedido_id}</b> está listo.<br>"
                                f"Haz clic en el botón para completar el pago.</div>"
                                f"<a href='{checkout_url}' target='_blank' "
                                f"style='background:#00C853;color:#0A0A0A;font-family:Bebas Neue,sans-serif;"
                                f"font-size:16px;letter-spacing:2px;padding:12px 32px;"
                                f"border-radius:3px;text-decoration:none;display:inline-block;'>"
                                f"PAGAR AHORA →</a>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.warning("Pedido registrado pero no se pudo generar el link de pago. Contacta a Térret.")

        with col_btn2:
            if st.button("VACIAR CARRITO", key="btn_vaciar"):
                st.session_state.carrito = []
                st.rerun()


# ─── LOGIN ADMIN ──────────────────────────────────────────────────────────────
def login_admin():
    st.markdown(
        "<div style='max-width:380px;margin:100px auto;text-align:center;'>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;letter-spacing:4px;"
        "margin-bottom:4px;'>⚡ TÉRRET MERCH</div>"
        "<div style='font-size:10px;color:#666;letter-spacing:3px;margin-bottom:40px;'>"
        "PANEL DE ADMINISTRACIÓN</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 2, 1])
    with col:
        pwd = st.text_input("Contraseña", type="password", key="admin_pwd",
                             placeholder="Contraseña de administrador")
        if st.button("ENTRAR", key="btn_admin_login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    st.stop()


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    params = st.query_params
    modo   = params.get("mode", "")
    equipo = params.get("equipo", "")

    client = conectar_sheets()
    if not client:
        st.error("No se pudo conectar con Google Sheets. Verifica los secrets.")
        return

    # Modo admin
    if modo == "admin":
        if not st.session_state.get("admin_logged"):
            login_admin()
        vista_admin(client)
        return

    # Modo tienda de equipo
    if equipo:
        vista_tienda(client, equipo)
        return

    # Landing — sin parámetros
    st.markdown(
        "<div style='max-width:600px;margin:120px auto;text-align:center;'>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:48px;letter-spacing:6px;"
        "margin-bottom:8px;'>⚡ TÉRRET</div>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:24px;letter-spacing:4px;"
        "color:#666;margin-bottom:24px;'>MERCH PERSONALIZADO</div>"
        "<div style='color:#666;font-size:14px;line-height:1.8;margin-bottom:40px;'>"
        "Este portal es exclusivo para equipos con colección personalizada.<br>"
        "Si tu equipo tiene una colección, ingresa con el enlace que te compartió tu coach."
        "</div>"
        "<div style='background:#111;border:1px solid #222;border-radius:6px;"
        "padding:20px;text-align:left;'>"
        "<div style='font-size:11px;color:#666;letter-spacing:2px;margin-bottom:12px;'>"
        "¿ERES COACH O ADMINISTRADOR DE ÉQUIPO?</div>"
        "<div style='font-size:13px;color:#888;'>Contacta a Térret para crear tu colección personalizada.<br>"
        "<a href='https://terretsports.com' style='color:#F5F0E8;'>terretsports.com</a></div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

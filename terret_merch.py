"""
TÉRRET MERCH — Plataforma de tiendas personalizadas por equipo
Streamlit + Google Sheets + Google Drive + Shopify Draft Orders

Modelo de datos:
  Equipos     → ID, Nombre, Codigo, Logo_Drive_ID, Color_Primario, Color_Secundario, Descripcion, Activo
  Colecciones → ID, Equipo_ID, Nombre, Temporada, Activa, Fecha_Corte
  Productos   → ID, Coleccion_ID, Nombre, Descripcion, Precio, Tallas, Colores, Drive_Folder_ID, Activo
  Pedidos     → ID, Fecha, Equipo_ID, Equipo_Nombre, Coleccion_ID, Coleccion_Nombre,
                Usuario_Nombre, Usuario_Email, Productos_JSON, Total,
                Shopify_Draft_ID, Shopify_Order_ID, Estado, Notas

Drive:
  Térret Tienda Custom/
    {Equipo}/
      logo.png
      {Temporada}/
        {Producto}/
          foto_1.jpg ...
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pandas as pd
import requests
import uuid
import io
import json
from datetime import datetime

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
DRIVE_ROOT_ID   = st.secrets.get("MERCH_DRIVE_ROOT_ID", "")
API_VERSION     = "2024-01"

HOJA_EQUIPOS     = "Equipos"
HOJA_COLECCIONES = "Colecciones"
HOJA_PRODUCTOS   = "Productos"
HOJA_PEDIDOS     = "Pedidos"

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

.stTextInput input, .stNumberInput input, .stSelectbox > div > div,
.stTextArea textarea {
    background: #111 !important;
    border: 1px solid #333 !important;
    color: #F5F0E8 !important;
    border-radius: 3px !important;
}

[data-testid="stRadio"] label { color: #F5F0E8 !important; }
[data-testid="stRadio"] p    { color: #F5F0E8 !important; }
[data-testid="stFileUploader"] {
    background: #111 !important;
    border: 1px dashed #333 !important;
    border-radius: 6px !important;
}

hr { border-color: #222 !important; }
#MainMenu, footer, header { visibility: hidden; }

.stTabs [data-baseweb="tab-list"] { background: #111; border-bottom: 1px solid #222; }
.stTabs [data-baseweb="tab"] { color: #666 !important; }
.stTabs [aria-selected="true"] { color: #F5F0E8 !important; border-bottom: 2px solid #F5F0E8; }

.stCheckbox label { color: #F5F0E8 !important; }
</style>
""", unsafe_allow_html=True)


# ─── GOOGLE AUTH ──────────────────────────────────────────────────────────────
@st.cache_resource(ttl=300)
def get_google_creds():
    try:
        return Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ],
        )
    except Exception as e:
        st.error(f"Error credenciales Google: {e}")
        return None


@st.cache_resource(ttl=300)
def conectar_sheets():
    creds = get_google_creds()
    if not creds:
        return None
    try:
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error Sheets: {e}")
        return None


@st.cache_resource(ttl=300)
def conectar_drive():
    creds = get_google_creds()
    if not creds:
        return None
    try:
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        st.error(f"Error Drive: {e}")
        return None


# ─── DRIVE HELPERS ────────────────────────────────────────────────────────────
# Todos los métodos usan supportsAllDrives=True e includeItemsFromAllDrives=True
# porque los archivos viven en una Unidad Compartida de Google Workspace.

def drive_get_or_create_folder(drive, nombre, parent_id):
    """Busca una subcarpeta por nombre dentro de parent_id. Si no existe, la crea."""
    q = (f"mimeType='application/vnd.google-apps.folder' "
         f"and name='{nombre}' "
         f"and '{parent_id}' in parents "
         f"and trashed=false")
    results = drive.files().list(
        q=q,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = drive.files().create(
        body=meta,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return folder["id"]


def drive_get_equipo_folder(drive, equipo_nombre):
    """Carpeta del equipo dentro de la Unidad Compartida raíz."""
    return drive_get_or_create_folder(drive, equipo_nombre, DRIVE_ROOT_ID)


def drive_get_coleccion_folder(drive, equipo_nombre, temporada):
    eq_folder = drive_get_equipo_folder(drive, equipo_nombre)
    return drive_get_or_create_folder(drive, temporada, eq_folder)


def drive_get_producto_folder(drive, equipo_nombre, temporada, producto_nombre):
    col_folder = drive_get_coleccion_folder(drive, equipo_nombre, temporada)
    return drive_get_or_create_folder(drive, producto_nombre, col_folder)


def drive_upload_file(drive, file_bytes, filename, mimetype, parent_id):
    """Sube un archivo a la Unidad Compartida y lo hace público de solo lectura."""
    media   = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype)
    meta    = {"name": filename, "parents": [parent_id]}
    f       = drive.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    file_id = f["id"]
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    return file_id, url


def drive_list_fotos(drive, folder_id):
    """Lista imágenes dentro de una carpeta de la Unidad Compartida."""
    if not folder_id:
        return []
    q = (f"'{folder_id}' in parents "
         f"and trashed=false "
         f"and mimeType contains 'image/'")
    results = drive.files().list(
        q=q,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    return [(f["id"], f"https://drive.google.com/uc?export=view&id={f['id']}") for f in files]


# ─── SHEETS HELPERS ───────────────────────────────────────────────────────────
def get_ws(client, nombre, headers=None):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            return sh.worksheet(nombre)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=nombre, rows=2000, cols=30)
            if headers:
                ws.append_row(headers)
                ws.format("1:1", {
                    "backgroundColor": {"red": 0.07, "green": 0.07, "blue": 0.07},
                    "textFormat": {
                        "foregroundColor": {"red": 0.96, "green": 0.94, "blue": 0.91},
                        "bold": True,
                    },
                })
            return ws
    except Exception as e:
        st.error(f"Error hoja '{nombre}': {e}")
        return None


@st.cache_data(ttl=60)
def leer_equipos(_client):
    ws = get_ws(_client, HOJA_EQUIPOS,
                ["ID", "Nombre", "Codigo", "Logo_Drive_ID", "Color_Primario",
                 "Color_Secundario", "Descripcion", "Activo"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Nombre", "Codigo", "Logo_Drive_ID", "Color_Primario",
                 "Color_Secundario", "Descripcion", "Activo"])


@st.cache_data(ttl=60)
def leer_colecciones(_client):
    ws = get_ws(_client, HOJA_COLECCIONES,
                ["ID", "Equipo_ID", "Nombre", "Temporada", "Activa", "Fecha_Corte"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Equipo_ID", "Nombre", "Temporada", "Activa", "Fecha_Corte"])


@st.cache_data(ttl=60)
def leer_productos(_client):
    ws = get_ws(_client, HOJA_PRODUCTOS,
                ["ID", "Coleccion_ID", "Nombre", "Descripcion", "Precio",
                 "Tallas", "Colores", "Drive_Folder_ID", "Activo"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Coleccion_ID", "Nombre", "Descripcion", "Precio",
                 "Tallas", "Colores", "Drive_Folder_ID", "Activo"])


@st.cache_data(ttl=30)
def leer_pedidos(_client):
    ws = get_ws(_client, HOJA_PEDIDOS,
                ["ID", "Fecha", "Equipo_ID", "Equipo_Nombre", "Coleccion_ID",
                 "Coleccion_Nombre", "Usuario_Nombre", "Usuario_Email",
                 "Productos_JSON", "Total", "Shopify_Draft_ID",
                 "Shopify_Order_ID", "Estado", "Notas"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Fecha", "Equipo_ID", "Equipo_Nombre", "Coleccion_ID",
                 "Coleccion_Nombre", "Usuario_Nombre", "Usuario_Email",
                 "Productos_JSON", "Total", "Shopify_Draft_ID",
                 "Shopify_Order_ID", "Estado", "Notas"])


def guardar_equipo(client, eq):
    ws = get_ws(client, HOJA_EQUIPOS)
    if not ws:
        return False
    try:
        ws.append_row([
            eq["id"], eq["nombre"], eq["codigo"], eq.get("logo_drive_id", ""),
            eq["color_primario"], eq["color_secundario"], eq["descripcion"], "SI",
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando equipo: {e}")
        return False


def guardar_coleccion(client, col):
    ws = get_ws(client, HOJA_COLECCIONES)
    if not ws:
        return False
    try:
        ws.append_row([
            col["id"], col["equipo_id"], col["nombre"],
            col["temporada"], "SI", col.get("fecha_corte", ""),
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando colección: {e}")
        return False


def guardar_producto(client, prod):
    ws = get_ws(client, HOJA_PRODUCTOS)
    if not ws:
        return False
    try:
        ws.append_row([
            prod["id"], prod["coleccion_id"], prod["nombre"],
            prod["descripcion"], prod["precio"], prod["tallas"],
            prod["colores"], prod.get("drive_folder_id", ""), "SI",
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando producto: {e}")
        return False


def guardar_pedido(client, pedido):
    ws = get_ws(client, HOJA_PEDIDOS)
    if not ws:
        return False
    try:
        ws.append_row([
            pedido["id"], pedido["fecha"], pedido["equipo_id"],
            pedido["equipo_nombre"], pedido["coleccion_id"], pedido["coleccion_nombre"],
            pedido["usuario_nombre"], pedido["usuario_email"],
            json.dumps(pedido["productos"], ensure_ascii=False),
            pedido["total"], pedido.get("shopify_draft_id", ""),
            pedido.get("shopify_order_id", ""), "PENDIENTE", pedido.get("notas", ""),
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando pedido: {e}")
        return False


def actualizar_coleccion_activa(client, coleccion_id, activa: bool):
    ws = get_ws(client, HOJA_COLECCIONES)
    if not ws:
        return False
    try:
        cell = ws.find(coleccion_id)
        if cell:
            ws.update_cell(cell.row, 5, "SI" if activa else "NO")
        st.cache_data.clear()
        return True
    except:
        return False


def actualizar_pedido_estado(client, pedido_id, order_id, estado="PAGADO"):
    ws = get_ws(client, HOJA_PEDIDOS)
    if not ws:
        return False
    try:
        cell = ws.find(pedido_id)
        if cell:
            ws.update_cell(cell.row, 12, order_id)
            ws.update_cell(cell.row, 13, estado)
        st.cache_data.clear()
        return True
    except:
        return False


def actualizar_logo_equipo(client, equipo_id, logo_drive_id):
    ws = get_ws(client, HOJA_EQUIPOS)
    if not ws:
        return False
    try:
        cell = ws.find(equipo_id)
        if cell:
            ws.update_cell(cell.row, 4, logo_drive_id)
        st.cache_data.clear()
        return True
    except:
        return False


# ─── SHOPIFY DRAFT ORDERS ─────────────────────────────────────────────────────
def crear_draft_order(items, usuario_email, usuario_nombre, equipo_nombre,
                      coleccion_nombre, pedido_id):
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
                {"name": "Talla",     "value": item.get("talla", "")},
                {"name": "Color",     "value": item.get("color", "")},
                {"name": "Equipo",    "value": equipo_nombre},
                {"name": "Colección", "value": coleccion_nombre},
            ],
        })

    nombre_parts = usuario_nombre.split()
    payload = {
        "draft_order": {
            "line_items": line_items,
            "customer": {
                "email":      usuario_email,
                "first_name": nombre_parts[0] if nombre_parts else "",
                "last_name":  " ".join(nombre_parts[1:]) if len(nombre_parts) > 1 else "",
            },
            "use_customer_default_address": False,
            "note": f"Pedido {pedido_id} — {equipo_nombre} / {coleccion_nombre}",
            "tags": f"merch,{equipo_nombre.lower().replace(' ', '-')}",
            "send_receipt": False,
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 201:
            return resp.json()["draft_order"], None
        return None, f"Error Shopify {resp.status_code}: {resp.text}"
    except Exception as e:
        return None, str(e)


# ─── UI HELPERS ───────────────────────────────────────────────────────────────
def seccion(titulo, subtitulo=""):
    sub = (f"<div style='font-size:11px;color:#666;letter-spacing:1px;margin-top:2px;'>"
           f"{subtitulo}</div>") if subtitulo else ""
    st.markdown(
        f"<div style='margin:32px 0 20px 0;padding-bottom:12px;border-bottom:1px solid #222;'>"
        f"<div style='font-family:Bebas Neue,sans-serif;font-size:22px;letter-spacing:3px;"
        f"color:#F5F0E8;'>{titulo}</div>{sub}</div>",
        unsafe_allow_html=True,
    )


def fmt_precio(v):
    try:
        return f"${float(str(v).replace(',', '')):,.0f}"
    except:
        return f"${v}"


# ─── PANEL ADMIN ──────────────────────────────────────────────────────────────
def vista_admin(client, drive):
    st.markdown(
        "<div style='display:flex;align-items:center;gap:16px;margin-bottom:32px;'>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;letter-spacing:4px;'>"
        "⚡ TÉRRET MERCH</div>"
        "<div style='background:#333;color:#888;font-size:10px;letter-spacing:2px;"
        "padding:4px 10px;border-radius:2px;font-family:DM Mono,monospace;'>PANEL ADMIN</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4 = st.tabs(["🏆 Equipos", "📅 Colecciones", "👕 Productos", "📋 Pedidos"])

    # ── TAB 1: EQUIPOS ────────────────────────────────────────────────────────
    with tab1:
        df_eq = leer_equipos(client)
        seccion("EQUIPOS", f"{len(df_eq)} equipos registrados")

        if not df_eq.empty:
            c1, c2 = st.columns(2)
            with c1: st.metric("Total", len(df_eq))
            with c2: st.metric("Activos", len(df_eq[df_eq["Activo"] == "SI"]))

            for _, eq in df_eq.iterrows():
                color   = eq.get("Color_Primario", "#F5F0E8") or "#F5F0E8"
                logo_id = eq.get("Logo_Drive_ID", "")
                logo_url = f"https://drive.google.com/uc?export=view&id={logo_id}" if logo_id else ""

                with st.expander(f"  {eq.get('Nombre','')}  ·  {eq.get('Codigo','')}"):
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        if logo_url:
                            st.image(logo_url, width=80)
                        else:
                            st.markdown(
                                "<div style='width:80px;height:80px;background:#1a1a1a;"
                                "border-radius:4px;display:flex;align-items:center;"
                                "justify-content:center;color:#333;font-size:24px;'>🏆</div>",
                                unsafe_allow_html=True,
                            )
                        logo_file = st.file_uploader(
                            "Subir logo", type=["png", "jpg", "jpeg", "webp"],
                            key=f"logo_up_{eq['ID']}",
                        )
                        if logo_file and st.button("GUARDAR LOGO", key=f"btn_logo_{eq['ID']}"):
                            with st.spinner("Subiendo logo..."):
                                eq_folder = drive_get_equipo_folder(drive, eq["Nombre"])
                                fid, _ = drive_upload_file(
                                    drive, logo_file.read(), "logo.png",
                                    logo_file.type, eq_folder,
                                )
                                if actualizar_logo_equipo(client, eq["ID"], fid):
                                    st.success("Logo actualizado")
                                    st.rerun()
                    with c2:
                        st.markdown(
                            f"<div style='font-size:12px;color:#666;line-height:2;'>"
                            f"<b style='color:#F5F0E8;'>Color primario:</b> "
                            f"<span style='background:{color};padding:2px 14px;"
                            f"border-radius:2px;'>&nbsp;</span> {color}<br>"
                            f"<b style='color:#F5F0E8;'>Descripción:</b> "
                            f"{eq.get('Descripcion','—')}<br>"
                            f"<b style='color:#F5F0E8;'>Link tienda:</b> "
                            f"<span style='font-family:DM Mono,monospace;font-size:11px;'>"
                            f"?equipo={eq.get('Codigo','')}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

        # Formulario nuevo equipo
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        with st.expander("➕ CREAR NUEVO EQUIPO"):
            c1, c2 = st.columns(2)
            with c1:
                eq_nombre = st.text_input("Nombre del equipo *", key="eq_nombre",
                                          placeholder="Ej: Atlético Running Club")
                eq_codigo = st.text_input("Código de acceso *", key="eq_codigo",
                                          placeholder="Ej: ARC2024")
            with c2:
                eq_color1 = st.color_picker("Color primario", "#F5F0E8", key="eq_color1")
                eq_color2 = st.color_picker("Color secundario", "#0A0A0A", key="eq_color2")

            eq_desc    = st.text_area("Descripción / mensaje", key="eq_desc",
                                      placeholder="Bienvenido al portal de merch oficial de…")
            logo_nuevo = st.file_uploader("Logo del equipo (opcional)",
                                          type=["png", "jpg", "jpeg", "webp"],
                                          key="logo_nuevo")

            if st.button("CREAR EQUIPO", key="btn_crear_eq"):
                if not eq_nombre or not eq_codigo:
                    st.error("Nombre y código son obligatorios.")
                else:
                    eq_id    = str(uuid.uuid4())[:8].upper()
                    logo_id  = ""
                    with st.spinner("Creando equipo en Drive y Sheets..."):
                        eq_folder = drive_get_equipo_folder(drive, eq_nombre)
                        if logo_nuevo:
                            fid, _ = drive_upload_file(
                                drive, logo_nuevo.read(), "logo.png",
                                logo_nuevo.type, eq_folder,
                            )
                            logo_id = fid
                        nuevo = {
                            "id": eq_id, "nombre": eq_nombre,
                            "codigo": eq_codigo.upper().strip(),
                            "logo_drive_id": logo_id,
                            "color_primario": eq_color1,
                            "color_secundario": eq_color2,
                            "descripcion": eq_desc,
                        }
                        if guardar_equipo(client, nuevo):
                            st.success(f"✅ Equipo **{eq_nombre}** creado")
                            st.info(f"🔗 Link: `?equipo={eq_codigo.upper()}`")

    # ── TAB 2: COLECCIONES ────────────────────────────────────────────────────
    with tab2:
        df_eq  = leer_equipos(client)
        df_col = leer_colecciones(client)
        seccion("COLECCIONES", f"{len(df_col)} colecciones registradas")

        if df_eq.empty:
            st.warning("Primero crea un equipo.")
        else:
            if not df_col.empty:
                for _, eq in df_eq.iterrows():
                    cols_eq = df_col[df_col["Equipo_ID"] == eq["ID"]]
                    if cols_eq.empty:
                        continue
                    color = eq.get("Color_Primario", "#F5F0E8") or "#F5F0E8"
                    st.markdown(
                        f"<div style='font-family:Bebas Neue,sans-serif;font-size:16px;"
                        f"letter-spacing:2px;color:{color};margin:24px 0 10px 0;'>"
                        f"{eq['Nombre']}</div>",
                        unsafe_allow_html=True,
                    )
                    for _, col in cols_eq.iterrows():
                        activa = col.get("Activa", "NO") == "SI"
                        c1, c2, c3 = st.columns([4, 2, 1])
                        with c1:
                            st.markdown(
                                f"<div style='background:#111;border:1px solid #222;"
                                f"border-radius:4px;padding:10px 14px;'>"
                                f"<div style='font-weight:600;'>{col.get('Nombre','')}</div>"
                                f"<div style='font-size:11px;color:#666;'>"
                                f"Temporada: {col.get('Temporada','—')} · "
                                f"Corte: {col.get('Fecha_Corte','—')}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        with c2:
                            st.markdown(
                                f"<div style='padding:10px 0;font-size:11px;"
                                f"color:{'#00C853' if activa else '#555'};'>"
                                f"{'🟢 ACTIVA' if activa else '⚫ INACTIVA'}</div>",
                                unsafe_allow_html=True,
                            )
                        with c3:
                            if st.button(
                                "DESACTIVAR" if activa else "ACTIVAR",
                                key=f"toggle_{col['ID']}",
                            ):
                                actualizar_coleccion_activa(client, col["ID"], not activa)
                                st.rerun()

            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            with st.expander("➕ CREAR NUEVA COLECCIÓN"):
                eq_opciones = {row["Nombre"]: row["ID"] for _, row in df_eq.iterrows()}
                c1, c2 = st.columns(2)
                with c1:
                    col_equipo = st.selectbox("Equipo *", list(eq_opciones.keys()), key="col_eq")
                    col_nombre = st.text_input("Nombre de la colección *", key="col_nombre",
                                               placeholder="Ej: Colección Verano 2025")
                with c2:
                    col_temp  = st.text_input("Temporada *", key="col_temp",
                                              placeholder="Ej: 2025-Q2")
                    col_corte = st.text_input("Fecha de corte", key="col_corte",
                                             placeholder="Ej: 30/06/2025")

                if st.button("CREAR COLECCIÓN", key="btn_crear_col"):
                    if not col_nombre or not col_temp:
                        st.error("Nombre y temporada son obligatorios.")
                    else:
                        col_id = str(uuid.uuid4())[:8].upper()
                        with st.spinner("Creando carpeta en Drive..."):
                            drive_get_coleccion_folder(drive, col_equipo, col_temp)
                        nueva = {
                            "id": col_id, "equipo_id": eq_opciones[col_equipo],
                            "nombre": col_nombre, "temporada": col_temp,
                            "fecha_corte": col_corte,
                        }
                        if guardar_coleccion(client, nueva):
                            st.success(f"✅ Colección **{col_nombre}** creada")

    # ── TAB 3: PRODUCTOS ──────────────────────────────────────────────────────
    with tab3:
        df_eq  = leer_equipos(client)
        df_col = leer_colecciones(client)
        df_pro = leer_productos(client)

        seccion("PRODUCTOS", f"{len(df_pro)} productos registrados")

        if df_eq.empty or df_col.empty:
            st.warning("Primero crea un equipo y una colección.")
        else:
            if not df_pro.empty:
                col_filtro = ["Todas"] + df_col["Nombre"].tolist()
                filtro = st.selectbox("Filtrar por colección:", col_filtro, key="filtro_col_prod")
                df_show = df_pro.copy()
                if filtro != "Todas":
                    col_id_f = df_col[df_col["Nombre"] == filtro]["ID"].iloc[0]
                    df_show  = df_pro[df_pro["Coleccion_ID"] == col_id_f]

                for _, p in df_show.iterrows():
                    col_row  = df_col[df_col["ID"] == p.get("Coleccion_ID", "")]
                    col_name = col_row["Nombre"].iloc[0] if not col_row.empty else "—"
                    fotos    = drive_list_fotos(drive, p.get("Drive_Folder_ID", ""))

                    with st.expander(
                        f"👕  {p.get('Nombre','')}  ·  "
                        f"{fmt_precio(p.get('Precio',0))}  ·  {col_name}"
                    ):
                        c1, c2 = st.columns([2, 3])
                        with c1:
                            if fotos:
                                st.image(fotos[0][1], use_container_width=True)
                                if len(fotos) > 1:
                                    st.markdown(
                                        f"<div style='font-size:11px;color:#666;'>"
                                        f"+{len(fotos)-1} fotos más en Drive</div>",
                                        unsafe_allow_html=True,
                                    )
                            else:
                                st.markdown(
                                    "<div style='height:120px;background:#1a1a1a;"
                                    "border-radius:4px;display:flex;align-items:center;"
                                    "justify-content:center;color:#333;font-size:28px;'>"
                                    "👕</div>",
                                    unsafe_allow_html=True,
                                )
                        with c2:
                            st.markdown(
                                f"<div style='font-size:12px;color:#888;line-height:2;'>"
                                f"<b style='color:#F5F0E8;'>Tallas:</b> {p.get('Tallas','—')}<br>"
                                f"<b style='color:#F5F0E8;'>Colores:</b> {p.get('Colores','—')}<br>"
                                f"<b style='color:#F5F0E8;'>Descripción:</b> "
                                f"{p.get('Descripcion','—')}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            nuevas_fotos = st.file_uploader(
                                "Agregar fotos (drag & drop múltiple)",
                                type=["jpg", "jpeg", "png", "webp"],
                                accept_multiple_files=True,
                                key=f"fotos_up_{p['ID']}",
                            )
                            if nuevas_fotos and st.button(
                                "SUBIR FOTOS", key=f"btn_fotos_{p['ID']}"
                            ):
                                folder_id = p.get("Drive_Folder_ID", "")
                                if not folder_id:
                                    st.error("Este producto no tiene carpeta en Drive.")
                                else:
                                    with st.spinner(f"Subiendo {len(nuevas_fotos)} foto(s)..."):
                                        for f_up in nuevas_fotos:
                                            drive_upload_file(
                                                drive, f_up.read(),
                                                f_up.name, f_up.type, folder_id,
                                            )
                                    st.success(f"✅ {len(nuevas_fotos)} foto(s) subidas")
                                    st.rerun()

            # Formulario nuevo producto
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            with st.expander("➕ AGREGAR PRODUCTO"):
                eq_opciones = {row["Nombre"]: row["ID"] for _, row in df_eq.iterrows()}
                prod_equipo = st.selectbox("Equipo *", list(eq_opciones.keys()), key="prod_eq")
                eq_id_sel   = eq_opciones[prod_equipo]
                cols_equipo = df_col[df_col["Equipo_ID"] == eq_id_sel]

                if cols_equipo.empty:
                    st.warning("Este equipo no tiene colecciones. Créalas primero.")
                else:
                    col_opciones = {
                        row["Nombre"]: (row["ID"], row["Temporada"])
                        for _, row in cols_equipo.iterrows()
                    }
                    prod_col              = st.selectbox("Colección *", list(col_opciones.keys()),
                                                         key="prod_col")
                    col_id_sel, col_temp_sel = col_opciones[prod_col]

                    c1, c2 = st.columns(2)
                    with c1:
                        prod_nombre  = st.text_input("Nombre del producto *", key="prod_nombre",
                                                     placeholder="Ej: Camiseta Running Pro")
                        prod_precio  = st.number_input("Precio (COP) *", min_value=0,
                                                       step=1000, key="prod_precio")
                        prod_tallas  = st.text_input("Tallas", key="prod_tallas",
                                                     placeholder="XS,S,M,L,XL,XXL")
                    with c2:
                        prod_colores = st.text_input("Colores", key="prod_colores",
                                                     placeholder="Negro,Blanco")
                        prod_desc    = st.text_area("Descripción", key="prod_desc",
                                                    placeholder="Material, detalles del diseño…")

                    prod_fotos = st.file_uploader(
                        "Fotos del producto (drag & drop múltiple)",
                        type=["jpg", "jpeg", "png", "webp"],
                        accept_multiple_files=True,
                        key="prod_fotos_new",
                    )

                    if st.button("AGREGAR PRODUCTO", key="btn_add_prod"):
                        if not prod_nombre or prod_precio <= 0:
                            st.error("Nombre y precio son obligatorios.")
                        else:
                            prod_id = str(uuid.uuid4())[:8].upper()
                            with st.spinner("Creando producto en Drive y Sheets..."):
                                folder_id = drive_get_producto_folder(
                                    drive, prod_equipo, col_temp_sel, prod_nombre,
                                )
                                if prod_fotos:
                                    for f_up in prod_fotos:
                                        drive_upload_file(
                                            drive, f_up.read(),
                                            f_up.name, f_up.type, folder_id,
                                        )
                                nuevo = {
                                    "id": prod_id, "coleccion_id": col_id_sel,
                                    "nombre": prod_nombre, "descripcion": prod_desc,
                                    "precio": prod_precio, "tallas": prod_tallas,
                                    "colores": prod_colores, "drive_folder_id": folder_id,
                                }
                                if guardar_producto(client, nuevo):
                                    n = len(prod_fotos) if prod_fotos else 0
                                    st.success(f"✅ **{prod_nombre}** agregado con {n} foto(s)")

    # ── TAB 4: PEDIDOS ────────────────────────────────────────────────────────
    with tab4:
        df_ped = leer_pedidos(client)
        seccion("PEDIDOS", f"{len(df_ped)} pedidos registrados")

        if df_ped.empty:
            st.info("Aún no hay pedidos.")
        else:
            pagados    = len(df_ped[df_ped["Estado"] == "PAGADO"])
            pendientes = len(df_ped[df_ped["Estado"] == "PENDIENTE"])
            total_cop  = df_ped["Total"].apply(
                lambda x: float(str(x).replace(",", "")) if x else 0
            ).sum()

            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Total pedidos", len(df_ped))
            with c2: st.metric("Pagados",       pagados)
            with c3: st.metric("Pendientes",    pendientes)
            with c4: st.metric("Valor total",   fmt_precio(total_cop))

            c1, c2 = st.columns(2)
            with c1:
                equipos_list = ["Todos"] + df_ped["Equipo_Nombre"].dropna().unique().tolist()
                filtro_eq = st.selectbox("Equipo:", equipos_list, key="filtro_eq_ped")
            with c2:
                estados    = ["Todos", "PENDIENTE", "PAGADO", "PRODUCCION", "ENVIADO"]
                filtro_est = st.selectbox("Estado:", estados, key="filtro_est_ped")

            df_show = df_ped.copy()
            if filtro_eq  != "Todos": df_show = df_show[df_show["Equipo_Nombre"] == filtro_eq]
            if filtro_est != "Todos": df_show = df_show[df_show["Estado"] == filtro_est]

            for _, p in df_show.sort_values("Fecha", ascending=False).iterrows():
                estado = p.get("Estado", "PENDIENTE")
                color_estado = {
                    "PAGADO": "#00C853", "PENDIENTE": "#FFB800",
                    "PRODUCCION": "#4488FF", "ENVIADO": "#2D6A4F",
                }.get(estado, "#666")

                try:
                    prods     = json.loads(p.get("Productos_JSON", "[]"))
                    prods_str = " · ".join([
                        f"{pr['nombre']} ({pr.get('talla','')}/{pr.get('color','')}) x{pr['cantidad']}"
                        for pr in prods
                    ])
                except:
                    prods_str = str(p.get("Productos_JSON", ""))

                st.markdown(
                    f"<div style='background:#111;border:1px solid #222;border-radius:6px;"
                    f"padding:14px 18px;margin-bottom:8px;'>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;margin-bottom:6px;'>"
                    f"<div><span style='font-weight:600;'>{p.get('Usuario_Nombre','—')}</span>"
                    f"<span style='color:#666;font-size:12px;margin-left:10px;'>"
                    f"{p.get('Usuario_Email','')}</span></div>"
                    f"<div style='display:flex;gap:10px;align-items:center;'>"
                    f"<span style='font-family:Bebas Neue,sans-serif;font-size:18px;'>"
                    f"{fmt_precio(p.get('Total',0))}</span>"
                    f"<span style='background:{color_estado}22;color:{color_estado};"
                    f"font-size:9px;letter-spacing:1.5px;padding:3px 8px;border-radius:2px;"
                    f"font-family:DM Mono,monospace;'>{estado}</span>"
                    f"</div></div>"
                    f"<div style='font-size:11px;color:#888;'>"
                    f"{p.get('Equipo_Nombre','—')} · {p.get('Coleccion_Nombre','—')} · "
                    f"{p.get('Fecha','—')} · ID: {p.get('ID','—')}</div>"
                    f"<div style='font-size:11px;color:#666;margin-top:4px;'>{prods_str}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            if st.button("📥 EXPORTAR CSV PRODUCCIÓN", key="btn_export"):
                csv = df_show.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Descargar CSV",
                    csv,
                    f"pedidos_terret_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv",
                    key="dl_csv",
                )


# ─── VISTA TIENDA ─────────────────────────────────────────────────────────────
def vista_tienda(client, drive, codigo_equipo):
    df_eq  = leer_equipos(client)
    df_col = leer_colecciones(client)
    df_pro = leer_productos(client)

    eq_row = df_eq[df_eq["Codigo"].str.upper() == codigo_equipo.upper()]
    if eq_row.empty:
        st.markdown(
            "<div style='max-width:480px;margin:120px auto;text-align:center;'>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;"
            "letter-spacing:3px;margin-bottom:12px;'>COLECCIÓN NO ENCONTRADA</div>"
            "<div style='color:#666;font-size:14px;'>El código no es válido.<br>"
            "Verifica con tu coach o con Térret.</div></div>",
            unsafe_allow_html=True,
        )
        return

    eq        = eq_row.iloc[0]
    eq_id     = eq["ID"]
    eq_nombre = eq["Nombre"]
    eq_color  = eq.get("Color_Primario", "#F5F0E8") or "#F5F0E8"
    eq_desc   = eq.get("Descripcion", "")
    logo_id   = eq.get("Logo_Drive_ID", "")
    logo_url  = f"https://drive.google.com/uc?export=view&id={logo_id}" if logo_id else ""

    cols_activas = df_col[
        (df_col["Equipo_ID"] == eq_id) & (df_col["Activa"] == "SI")
    ]

    # Header
    logo_html = (
        f"<img src='{logo_url}' style='height:52px;object-fit:contain;"
        f"margin-right:16px;border-radius:4px;'>"
        if logo_url else ""
    )
    st.markdown(
        f"<div style='border-bottom:1px solid #222;padding:20px 0 20px 0;"
        f"margin-bottom:28px;display:flex;align-items:center;'>"
        f"{logo_html}"
        f"<div>"
        f"<div style='font-size:10px;color:#666;letter-spacing:3px;"
        f"font-family:DM Mono,monospace;margin-bottom:4px;'>Colección Exclusiva</div>"
        f"<div style='font-family:Bebas Neue,sans-serif;font-size:32px;"
        f"letter-spacing:4px;color:{eq_color};'>{eq_nombre.upper()}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    if eq_desc:
        st.markdown(
            f"<div style='color:#888;font-size:14px;margin-bottom:20px;'>{eq_desc}</div>",
            unsafe_allow_html=True,
        )

    if cols_activas.empty:
        st.markdown(
            "<div style='text-align:center;padding:80px;color:#666;'>"
            "No hay colecciones activas en este momento.<br>"
            "Contacta a Térret para más información.</div>",
            unsafe_allow_html=True,
        )
        return

    if "carrito" not in st.session_state:
        st.session_state.carrito = []

    # Colecciones activas
    for _, col in cols_activas.iterrows():
        col_id     = col["ID"]
        col_nombre = col["Nombre"]
        col_corte  = col.get("Fecha_Corte", "")

        if df_pro.empty or "Coleccion_ID" not in df_pro.columns:
            productos = pd.DataFrame()
        else:
            productos = df_pro[
                (df_pro["Coleccion_ID"] == col_id) & (df_pro["Activo"] == "SI")
            ]

        corte_html = (
            f"<div style='background:#1a1a00;border:1px solid #333300;"
            f"border-radius:4px;padding:6px 12px;margin-top:8px;"
            f"font-size:12px;color:#FFB800;display:inline-block;'>"
            f"⏰ Pedidos hasta: <b>{col_corte}</b></div>"
            if col_corte else ""
        )
        st.markdown(
            f"<div style='margin:24px 0 16px 0;padding-bottom:10px;"
            f"border-bottom:1px solid #1a1a1a;'>"
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:18px;"
            f"letter-spacing:2px;color:{eq_color};'>{col_nombre.upper()}</div>"
            f"{corte_html}</div>",
            unsafe_allow_html=True,
        )

        if productos.empty:
            st.markdown(
                "<div style='color:#555;font-size:13px;padding:20px 0;'>"
                "Sin productos en esta colección aún.</div>",
                unsafe_allow_html=True,
            )
            continue

        cols_grid = st.columns(3)
        for i, (_, prod) in enumerate(productos.iterrows()):
            with cols_grid[i % 3]:
                precio  = float(str(prod.get("Precio", 0)).replace(",", "") or 0)
                tallas  = [t.strip() for t in str(prod.get("Tallas", "")).split(",") if t.strip()]
                colores = [c.strip() for c in str(prod.get("Colores", "")).split(",") if c.strip()]
                fotos   = drive_list_fotos(drive, prod.get("Drive_Folder_ID", ""))

                img_html = (
                    f"<img src='{fotos[0][1]}' style='width:100%;height:200px;"
                    f"object-fit:cover;border-radius:4px 4px 0 0;'>"
                    if fotos else
                    f"<div style='width:100%;height:200px;background:#1a1a1a;"
                    f"border-radius:4px 4px 0 0;display:flex;align-items:center;"
                    f"justify-content:center;color:#333;font-size:32px;'>👕</div>"
                )

                desc = str(prod.get("Descripcion", "") or "")
                desc_short = desc[:80] + "…" if len(desc) > 80 else desc

                st.markdown(
                    f"<div style='background:#111;border:1px solid #222;"
                    f"border-radius:6px;margin-bottom:8px;overflow:hidden;'>"
                    f"{img_html}"
                    f"<div style='padding:14px;'>"
                    f"<div style='font-weight:600;font-size:14px;margin-bottom:4px;'>"
                    f"{prod.get('Nombre','')}</div>"
                    f"<div style='font-size:12px;color:#666;margin-bottom:8px;'>{desc_short}</div>"
                    f"<div style='font-family:Bebas Neue,sans-serif;font-size:22px;"
                    f"color:{eq_color};'>{fmt_precio(precio)}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

                prod_key  = f"prod_{prod['ID']}"
                talla_sel = st.selectbox("Talla", tallas, key=f"talla_{prod_key}") if tallas else ""
                color_sel = st.selectbox("Color", colores, key=f"color_{prod_key}") if colores else ""
                cant      = st.number_input("Cantidad", min_value=1, max_value=20,
                                            value=1, key=f"cant_{prod_key}")

                if st.button("AGREGAR AL CARRITO", key=f"add_{prod_key}"):
                    st.session_state.carrito.append({
                        "prod_id":          prod["ID"],
                        "nombre":           prod["Nombre"],
                        "precio":           precio,
                        "talla":            talla_sel,
                        "color":            color_sel,
                        "cantidad":         int(cant),
                        "coleccion_id":     col_id,
                        "coleccion_nombre": col_nombre,
                    })
                    st.success(f"✅ {prod['Nombre']} agregado")

    # ── CARRITO ───────────────────────────────────────────────────────────────
    if st.session_state.carrito:
        seccion("TU PEDIDO", "Revisa y confirma antes de pagar")

        total = 0
        for idx, item in enumerate(st.session_state.carrito):
            subtotal = item["precio"] * item["cantidad"]
            total   += subtotal
            c1, c2, c3 = st.columns([4, 2, 1])
            with c1:
                st.markdown(
                    f"<div style='padding:10px 0;border-bottom:1px solid #1a1a1a;'>"
                    f"<div style='font-weight:500;'>{item['nombre']}</div>"
                    f"<div style='font-size:11px;color:#666;'>"
                    f"Talla: {item['talla']} · Color: {item['color']} · "
                    f"x{item['cantidad']} · {item.get('coleccion_nombre','')}</div></div>",
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
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:16px;"
            f"letter-spacing:2px;'>TOTAL</div>"
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:28px;"
            f"color:{eq_color};'>{fmt_precio(total)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        seccion("TUS DATOS", "Para procesar tu pedido")
        c1, c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Nombre completo *", key="buyer_nombre",
                                   placeholder="Como quieres que aparezca en el pedido")
        with c2:
            email = st.text_input("Correo electrónico *", key="buyer_email",
                                  placeholder="Para enviarte la confirmación")

        notas = st.text_area("Notas adicionales", key="buyer_notas",
                             placeholder="Dirección de envío, instrucciones especiales…")

        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn1:
            if st.button("🛒 PROCEDER AL PAGO", key="btn_pagar"):
                if not nombre or not email:
                    st.error("Nombre y correo son obligatorios.")
                elif "@" not in email:
                    st.error("El correo no es válido.")
                else:
                    pedido_id      = f"TM-{str(uuid.uuid4())[:6].upper()}"
                    col_id_pedido  = st.session_state.carrito[0].get("coleccion_id", "")
                    col_nom_pedido = st.session_state.carrito[0].get("coleccion_nombre", "")

                    with st.spinner("Creando tu orden…"):
                        draft, err = crear_draft_order(
                            items=st.session_state.carrito,
                            usuario_email=email,
                            usuario_nombre=nombre,
                            equipo_nombre=eq_nombre,
                            coleccion_nombre=col_nom_pedido,
                            pedido_id=pedido_id,
                        )

                    if err or not draft:
                        st.error(f"Error creando la orden: {err}")
                    else:
                        pedido_data = {
                            "id":               pedido_id,
                            "fecha":            datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "equipo_id":        eq_id,
                            "equipo_nombre":    eq_nombre,
                            "coleccion_id":     col_id_pedido,
                            "coleccion_nombre": col_nom_pedido,
                            "usuario_nombre":   nombre,
                            "usuario_email":    email,
                            "productos":        st.session_state.carrito,
                            "total":            total,
                            "shopify_draft_id": draft["id"],
                            "notas":            notas,
                        }
                        guardar_pedido(client, pedido_data)
                        checkout_url = draft.get("invoice_url", "")

                        if checkout_url:
                            st.session_state.carrito = []
                            st.markdown(
                                f"<div style='background:#0a1a0a;border:1px solid #1a3a1a;"
                                f"border-radius:6px;padding:24px;text-align:center;'>"
                                f"<div style='font-family:Bebas Neue,sans-serif;font-size:20px;"
                                f"color:#00C853;letter-spacing:2px;margin-bottom:8px;'>"
                                f"✅ PEDIDO REGISTRADO</div>"
                                f"<div style='color:#888;font-size:13px;margin-bottom:16px;'>"
                                f"Tu pedido <b style='color:#F5F0E8;'>{pedido_id}</b> está listo.<br>"
                                f"Haz clic para completar el pago.</div>"
                                f"<a href='{checkout_url}' target='_blank' "
                                f"style='background:#00C853;color:#0A0A0A;"
                                f"font-family:Bebas Neue,sans-serif;font-size:16px;"
                                f"letter-spacing:2px;padding:12px 32px;border-radius:3px;"
                                f"text-decoration:none;display:inline-block;'>"
                                f"PAGAR AHORA →</a></div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.warning(
                                "Pedido registrado pero no se generó el link de pago. "
                                "Contacta a Térret."
                            )

        with col_btn2:
            if st.button("VACIAR CARRITO", key="btn_vaciar"):
                st.session_state.carrito = []
                st.rerun()


# ─── LOGIN ADMIN ──────────────────────────────────────────────────────────────
def login_admin():
    st.markdown(
        "<div style='max-width:380px;margin:100px auto;text-align:center;'>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;"
        "letter-spacing:4px;margin-bottom:4px;'>⚡ TÉRRET MERCH</div>"
        "<div style='font-size:10px;color:#666;letter-spacing:3px;"
        "margin-bottom:40px;'>PANEL DE ADMINISTRACIÓN</div></div>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 2, 1])
    with col:
        pwd = st.text_input("Contraseña", type="password", key="admin_pwd")
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
    drive  = conectar_drive()

    if not client:
        st.error("No se pudo conectar con Google Sheets.")
        return
    if not drive:
        st.error("No se pudo conectar con Google Drive.")
        return

    if modo == "admin":
        if not st.session_state.get("admin_logged"):
            login_admin()
        vista_admin(client, drive)
        return

    if equipo:
        vista_tienda(client, drive, equipo)
        return

    # Landing
    st.markdown(
        "<div style='max-width:600px;margin:120px auto;text-align:center;'>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:52px;"
        "letter-spacing:6px;margin-bottom:6px;'>⚡ TÉRRET</div>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:24px;"
        "letter-spacing:4px;color:#666;margin-bottom:28px;'>MERCH PERSONALIZADO</div>"
        "<div style='color:#666;font-size:14px;line-height:1.9;margin-bottom:40px;'>"
        "Este portal es exclusivo para equipos con colección personalizada.<br>"
        "Si tu equipo tiene una colección, ingresa con el enlace que te compartió tu coach."
        "</div>"
        "<div style='background:#111;border:1px solid #222;border-radius:6px;"
        "padding:20px;text-align:left;'>"
        "<div style='font-size:11px;color:#666;letter-spacing:2px;margin-bottom:12px;'>"
        "¿ERES COACH O ADMINISTRADOR DE ÉQUIPO?</div>"
        "<div style='font-size:13px;color:#888;'>"
        "Contacta a Térret para crear tu colección personalizada.<br>"
        "<a href='https://terretsports.com' style='color:#F5F0E8;'>terretsports.com</a>"
        "</div></div></div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

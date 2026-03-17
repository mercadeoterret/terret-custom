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
    initial_sidebar_state="auto",
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

# ─── SVG LOGO ─────────────────────────────────────────────────────────────────
LOGO_SVG = """<svg viewBox="0 0 438.53 94.81" xmlns="http://www.w3.org/2000/svg" style="height:28px;width:auto;display:inline-block;vertical-align:middle;">
  <path d="M122.44.87c-.39-.45-.97-.7-1.59-.7H5.05c-.91,0-1.7.65-1.88,1.55L.06,18.85c-.11.56.04,1.15.4,1.59.36.44.9.7,1.47.7h21.41l-14.26,71.11c-.11.56.03,1.15.4,1.59.36.44.91.7,1.48.7h18.99c.91,0,1.7-.65,1.87-1.55l14.41-71.85h10.73l-15.3,71.33c-.12.56.04,1.15.43,1.6.39.44.98.7,1.59.7h59.15c.99,0,1.83-.65,2.02-1.55l3.36-16.01c.12-.56-.04-1.14-.43-1.59-.39-.45-.98-.7-1.59-.7h-36.2l4.27-19.18h30.06c.99,0,1.83-.65,2.02-1.55l3.36-16.01c.12-.56-.04-1.14-.43-1.59-.39-.45-.97-.7-1.59-.7h-29.29l3.88-14.74h35.79c.99,0,1.83-.65,2.02-1.55l2.8-17.13c.12-.56-.04-1.14-.43-1.59Z" fill="#FFFFFF"/>
  <path d="M406.71.86c-.36-.44-.9-.7-1.47-.7h-114.07c-.98,0-1.83.65-2.02,1.55l-19.46,90.75c-.12.56.04,1.15.43,1.6.39.44.98.7,1.59.7h59.15c.99,0,1.83-.65,2.02-1.55l3.36-16.01c.12-.56-.04-1.14-.43-1.59-.39-.45-.98-.7-1.59-.7h-36.2l4.27-19.18h30.06c.99,0,1.83-.65,2.02-1.55l3.36-16.01c.12-.56-.04-1.14-.43-1.59-.39-.45-.97-.7-1.59-.7h-29.29l3.88-14.74h46.78l-14.26,71.11c-.11.56.03,1.15.4,1.59.36.44.91.7,1.48.7h18.99c.91,0,1.7-.65,1.87-1.55l14.41-71.85h22.17c.91,0,1.7-.65,1.88-1.55l3.11-17.14c.11-.56-.04-1.15-.4-1.59Z" fill="#FFFFFF"/>
  <path d="M162.5.11h-28.51c-.92,0-1.71.65-1.89,1.55l-18.17,90.85c-.11.56.03,1.15.4,1.6.37.44.91.7,1.49.7h19.11c.92,0,1.71-.65,1.89-1.55l6.27-30.07h8.24l11.25,30.34c.27.77,1,1.29,1.82,1.29h20.13c.64,0,1.23-.32,1.59-.84.36-.52.43-1.19.2-1.79l-13.4-34.18c14.59-5.58,22.59-17.13,22.59-32.73S183.78.11,162.5.11ZM151.52,21.25h7.97c11.74,0,13.28,3.78,13.28,7.98,0,9.31-6.56,13.29-18.47,13.29h-7.32l4.54-21.27Z" fill="#FFFFFF"/>
  <path d="M237.54,0h-28.51c-.92,0-1.71.65-1.89,1.55l-18.17,90.85c-.11.56.03,1.15.4,1.6.37.44.91.7,1.49.7h19.11c.92,0,1.71-.65,1.89-1.55l6.27-30.07h8.24l11.25,30.34c.27.77,1,1.29,1.82,1.29h20.13c.64,0,1.23-.32,1.59-.84.36-.52.43-1.19.2-1.79l-13.4-34.18c14.59-5.58,22.59-17.13,22.59-32.73S258.82,0,237.54,0ZM226.56,21.14h7.97c11.74,0,13.28,3.78,13.28,7.98,0,9.31-6.56,13.29-18.47,13.29h-7.32l4.54-21.27Z" fill="#FFFFFF"/>
  <path d="M437.97,10.77c.11,5.77-4.84,10.72-10.68,10.67-5.85-.04-10.53-4.73-10.65-10.49-.12-5.83,4.7-10.71,10.36-10.86,6.05-.16,11.09,4.92,10.97,10.68ZM427.3,19.31c4.68.03,8.53-3.78,8.58-8.46.05-4.87-4.02-8.47-8.2-8.64-4.88-.19-8.86,3.88-8.92,8.42-.06,4.8,4.02,8.78,8.54,8.68Z" fill="#FFFFFF" fill-rule="evenodd"/>
  <path d="M428.31,4.45h-3.66c-.12,0-.22.08-.24.2l-2.33,11.67c-.01.07,0,.15.05.21.05.06.12.09.19.09h2.46c.12,0,.22-.08.24-.2l.81-3.86h1.06l1.44,3.9c.03.1.13.17.23.17h2.59c.08,0,.16-.04.2-.11.05-.07.06-.15.03-.23l-1.72-4.39c1.87-.72,2.9-2.2,2.9-4.2s-1.51-3.23-4.24-3.23ZM426.9,7.17h1.02c1.51,0,1.71.49,1.71,1.02,0,1.2-.84,1.71-2.37,1.71h-.94l.58-2.73Z" fill="#FFFFFF"/>
</svg>"""

# ─── ESTILOS QUIRÚRGICOS ──────────────────────────────────────────────────────
st.markdown("""
<style>
/* Ocultar chrome de Streamlit */
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: #0A0A0A !important; }

/* Reducir padding top */
[data-testid="stMainBlockContainer"] { padding-top: 0.5rem !important; }
[data-testid="stSidebarContent"] { padding-top: 1rem !important; }

/* Sidebar sin borde derecho visible */
[data-testid="stSidebar"] { border-right: 1px solid #1A1A1A !important; }

/* Labels uppercase monospace */
label, .stTextInput label, .stNumberInput label,
.stSelectbox label, .stTextArea label, .stDateInput label,
.stFileUploader label, .stMultiSelect label {
    font-size: 10px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: #555 !important;
}

/* Botones Bebas Neue */
.stButton > button {
    font-family: 'Bebas Neue', sans-serif !important;
    letter-spacing: 2.5px !important;
    font-size: 13px !important;
    border-radius: 2px !important;
    transition: opacity 0.15s !important;
}
.stButton > button:hover { opacity: 0.82 !important; }

/* Tabs estilo Terret */
.stTabs [data-baseweb="tab-list"] {
    border-bottom: 1px solid #1A1A1A !important;
    background: transparent !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 10px !important;
    letter-spacing: 2.5px !important;
    text-transform: uppercase !important;
    padding: 12px 20px !important;
    border-radius: 0 !important;
    color: #444 !important;
}
.stTabs [aria-selected="true"] {
    color: #FFF !important;
    border-bottom: 1px solid #FFF !important;
}

/* Métricas */
[data-testid="stMetricValue"] {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 2.4rem !important;
    letter-spacing: 1px !important;
}
[data-testid="stMetricLabel"] {
    font-size: 9px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: #444 !important;
}

/* Scrollbar minimalista */
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
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
    url = f"https://lh3.googleusercontent.com/d/{file_id}"
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
    return [(f["id"], f"https://lh3.googleusercontent.com/d/{f['id']}") for f in files]


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
                ["ID", "Nombre", "Codigo", "PIN", "Logo_Drive_ID", "Color_Primario",
                 "Color_Secundario", "Descripcion", "Activo"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records(expected_headers=["ID", "Nombre", "Codigo", "Logo_Drive_ID", "Color_Primario", "Color_Secundario", "Descripcion", "Activo"])
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Nombre", "Codigo", "PIN", "Logo_Drive_ID", "Color_Primario",
                 "Color_Secundario", "Descripcion", "Activo"])


@st.cache_data(ttl=60)
def leer_colecciones(_client):
    ws = get_ws(_client, HOJA_COLECCIONES,
                ["ID", "Equipo_ID", "Nombre", "Temporada", "Activa", "Fecha_Corte"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records(expected_headers=["ID", "Equipo_ID", "Nombre", "Temporada", "Activa", "Fecha_Corte"])
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Equipo_ID", "Nombre", "Temporada", "Activa", "Fecha_Corte"])


@st.cache_data(ttl=60)
def leer_productos(_client):
    ws = get_ws(_client, HOJA_PRODUCTOS,
                ["ID", "Coleccion_ID", "Nombre", "Descripcion", "Precio",
                 "Tallas", "Colores", "Drive_Folder_ID", "Fotos_URLs", "Personalizable", "Activo"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records(expected_headers=["ID", "Coleccion_ID", "Nombre", "Descripcion", "Precio", "Tallas", "Colores", "Drive_Folder_ID", "Fotos_URLs", "Personalizable", "Activo"])
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Coleccion_ID", "Nombre", "Descripcion", "Precio",
                 "Tallas", "Colores", "Drive_Folder_ID", "Fotos_URLs", "Personalizable", "Activo"])


@st.cache_data(ttl=30)
def leer_pedidos(_client):
    ws = get_ws(_client, HOJA_PEDIDOS,
                ["ID", "Fecha", "Equipo_ID", "Equipo_Nombre", "Coleccion_ID",
                 "Coleccion_Nombre", "Usuario_Nombre", "Usuario_Email",
                 "Productos_JSON", "Total", "Shopify_Draft_ID",
                 "Shopify_Order_ID", "Invoice_URL", "Estado", "Notas"])
    if not ws:
        return pd.DataFrame()
    data = ws.get_all_records(expected_headers=["ID", "Fecha", "Equipo_ID", "Equipo_Nombre", "Coleccion_ID", "Coleccion_Nombre", "Usuario_Nombre", "Usuario_Email", "Productos_JSON", "Total", "Shopify_Draft_ID", "Shopify_Order_ID", "Invoice_URL", "Estado", "Notas"])
    return pd.DataFrame(data) if data else pd.DataFrame(
        columns=["ID", "Fecha", "Equipo_ID", "Equipo_Nombre", "Coleccion_ID",
                 "Coleccion_Nombre", "Usuario_Nombre", "Usuario_Email",
                 "Productos_JSON", "Total", "Shopify_Draft_ID",
                 "Shopify_Order_ID", "Invoice_URL", "Estado", "Notas"])


def guardar_equipo(client, eq):
    ws = get_ws(client, HOJA_EQUIPOS)
    if not ws:
        return False
    try:
        ws.append_row([
            eq["id"], eq["nombre"], eq["codigo"], eq.get("pin", ""),
            eq.get("logo_drive_id", ""),
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
            prod["colores"], prod.get("drive_folder_id", ""),
            prod.get("fotos_urls", ""), prod.get("personalizable", "NO"), "SI",
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
            pedido.get("shopify_order_id", ""), pedido.get("invoice_url", ""),
            "PENDIENTE", pedido.get("notas", ""),
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando pedido: {e}")
        return False


def actualizar_pin_equipo(client, equipo_id, nuevo_pin):
    """Actualiza el PIN de acceso de un equipo."""
    ws = get_ws(client, HOJA_EQUIPOS)
    if not ws:
        return False
    try:
        cell = ws.find(equipo_id)
        if cell:
            ws.update_cell(cell.row, 4, str(nuevo_pin))  # col 4 = PIN
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error actualizando PIN: {e}")
        return False


def actualizar_fotos_producto(client, producto_id, fotos_urls_str):
    """Guarda la lista de URLs de fotos (separadas por coma) en la columna Fotos_URLs."""
    ws = get_ws(client, HOJA_PRODUCTOS)
    if not ws:
        return False
    try:
        cell = ws.find(producto_id)
        if cell:
            ws.update_cell(cell.row, 9, fotos_urls_str)  # columna 9 = Fotos_URLs
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error actualizando fotos: {e}")
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
            ws.update_cell(cell.row, 5, logo_drive_id)
        st.cache_data.clear()
        return True
    except:
        return False




def desactivar_registro(client, hoja, registro_id, col_activo):
    """Cambia Activo a NO en cualquier hoja. col_activo es el número de columna (1-based)."""
    ws = get_ws(client, hoja)
    if not ws:
        return False
    try:
        cell = ws.find(registro_id)
        if cell:
            ws.update_cell(cell.row, col_activo, "NO")
        st.cache_data.clear()
        return True
    except:
        return False


def eliminar_registro(client, hoja, registro_id):
    """Elimina la fila de un registro del Sheets definitivamente."""
    ws = get_ws(client, hoja)
    if not ws:
        return False
    try:
        cell = ws.find(registro_id)
        if cell:
            ws.delete_rows(cell.row)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error eliminando registro: {e}")
        return False


def drive_eliminar_carpeta(drive, folder_id):
    """Mueve una carpeta de Drive a la papelera."""
    if not folder_id:
        return False
    try:
        drive.files().update(
            fileId=folder_id,
            body={"trashed": True},
            supportsAllDrives=True,
        ).execute()
        return True
    except:
        return False


def tiene_pedidos(df_ped, campo, valor):
    """Verifica si existen pedidos asociados a un equipo_id, coleccion_id o prod_id."""
    if df_ped.empty or campo not in df_ped.columns:
        return False
    return not df_ped[df_ped[campo] == valor].empty

# ─── SINCRONIZACIÓN DE PAGOS ─────────────────────────────────────────────────
def sincronizar_pagos(client):
    """
    Consulta Shopify por cada Draft Order PENDIENTE.
    Si la draft fue completada (tiene order_id), actualiza el estado a PAGADO en Sheets.
    Retorna (actualizados, errores).
    """
    if not SHOPIFY_TOKEN:
        return 0, ["No hay token de Shopify configurado."]

    ws = get_ws(client, HOJA_PEDIDOS)
    if not ws:
        return 0, ["No se pudo acceder a la hoja de Pedidos."]

    df_ped = leer_pedidos(client)
    if df_ped.empty:
        return 0, []

    pendientes = df_ped[
        (df_ped["Estado"] == "PENDIENTE") &
        (df_ped["Shopify_Draft_ID"].astype(str).str.strip() != "")
    ]

    if pendientes.empty:
        return 0, []

    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    actualizados = 0
    errores = []

    for _, ped in pendientes.iterrows():
        draft_id = str(ped.get("Shopify_Draft_ID", "")).strip()
        if not draft_id:
            continue
        try:
            url = f"https://{TIENDA_URL}/admin/api/{API_VERSION}/draft_orders/{draft_id}.json"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("draft_order", {})
                order_id = data.get("order_id")
                status   = data.get("status", "")
                if order_id or status == "completed":
                    cell = ws.find(ped["ID"])
                    if cell:
                        ws.update_cell(cell.row, 12, str(order_id or ""))  # Shopify_Order_ID
                        ws.update_cell(cell.row, 14, "PAGADO")             # Estado
                    actualizados += 1
            else:
                errores.append(f"Draft {draft_id}: HTTP {resp.status_code}")
        except Exception as e:
            errores.append(f"Draft {draft_id}: {e}")

    if actualizados > 0:
        st.cache_data.clear()

    return actualizados, errores


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
                {"name": "Talla",             "value": item.get("talla", "")},
                {"name": "Color",             "value": item.get("color", "")},
                {"name": "Equipo",            "value": equipo_nombre},
                {"name": "Colección",         "value": coleccion_nombre},
                {"name": "Nombre camiseta",   "value": item.get("nombre_camiseta", "")},
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
    sub = (f"<div style='font-size:10px;color:#555;letter-spacing:2px;margin-top:4px;"
           f"font-family:DM Mono,monospace;'>{subtitulo}</div>") if subtitulo else ""
    st.markdown(
        f"<div style='margin:36px 0 20px 0;padding-bottom:14px;border-bottom:1px solid #1E1E1E;'>"
        f"<div style='font-family:Bebas Neue,sans-serif;font-size:20px;letter-spacing:4px;"
        f"color:#FFFFFF;'>{titulo}</div>{sub}</div>",
        unsafe_allow_html=True,
    )


def fmt_precio(v):
    try:
        return f"${float(str(v).replace(',', '')):,.0f}"
    except:
        return f"${v}"


# ─── PANEL ADMIN ──────────────────────────────────────────────────────────────
def vista_admin(client, drive):
    # ── Sidebar admin ──────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"<div style='padding:8px 0 24px 0;border-bottom:1px solid #1A1A1A;"
            f"margin-bottom:24px;'>{LOGO_SVG}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='font-size:9px;color:#333;letter-spacing:3px;"
            "margin-bottom:20px;'>MERCH ADMIN</div>",
            unsafe_allow_html=True,
        )

        # Selector de tab en sidebar
        if "admin_tab" not in st.session_state:
            st.session_state.admin_tab = "equipos"

        nav_items = [
            ("equipos",     "🏆", "EQUIPOS"),
            ("colecciones", "📅", "COLECCIONES"),
            ("productos",   "👕", "PRODUCTOS"),
            ("pedidos",     "📋", "PEDIDOS"),
        ]
        for key, icon, label in nav_items:
            activo = st.session_state.admin_tab == key
            bg     = "#1A1A1A" if activo else "transparent"
            color  = "#FFFFFF" if activo else "#555555"
            border = "border-left:2px solid #FFF;" if activo else "border-left:2px solid transparent;"
            st.markdown(
                f"<div style='background:{bg};{border}padding:10px 14px;"
                f"margin-bottom:2px;border-radius:0 2px 2px 0;cursor:pointer;'>"
                f"<span style='font-size:10px;letter-spacing:2.5px;"
                f"color:{color};'>{icon} {label}</span></div>",
                unsafe_allow_html=True,
            )
            if st.button(label, key=f"nav_{key}",
                         help=label):
                st.session_state.admin_tab = key
                st.rerun()

        st.markdown("<div style='height:1px;background:#1A1A1A;margin:24px 0;'></div>",
                    unsafe_allow_html=True)
        st.markdown(
            "<a href='https://terret.co' target='_blank' "
            "style='font-size:10px;color:#333;letter-spacing:1px;"
            "text-decoration:none;'>terret.co ↗</a>",
            unsafe_allow_html=True,
        )

    # ── Contenido según tab activo ─────────────────────────────────────────────
    tab_activo = st.session_state.get("admin_tab", "equipos")

    # Indicador de sección activa en el header
    nombres_tab = {"equipos": "🏆 EQUIPOS", "colecciones": "📅 COLECCIONES",
                   "productos": "👕 PRODUCTOS", "pedidos": "📋 PEDIDOS"}
    st.markdown(
        f"<div style='border-bottom:1px solid #1A1A1A;padding-bottom:12px;"
        f"margin-bottom:4px;font-size:10px;color:#444;letter-spacing:3px;'>"
        f"{nombres_tab.get(tab_activo,'')}</div>",
        unsafe_allow_html=True,
    )

    if tab_activo == "equipos":
        df_eq = leer_equipos(client)
        seccion("EQUIPOS", f"{len(df_eq)} equipos registrados")

        if not df_eq.empty:
            eq_activos   = df_eq[df_eq["Activo"] == "SI"]
            eq_inactivos = df_eq[df_eq["Activo"] != "SI"]

            c1, c2 = st.columns(2)
            with c1: st.metric("Total", len(df_eq))
            with c2: st.metric("Activos", len(eq_activos))

            for _, eq in eq_activos.iterrows():
                color   = eq.get("Color_Primario", "#F5F0E8") or "#F5F0E8"
                logo_id = eq.get("Logo_Drive_ID", "")
                logo_url = f"https://lh3.googleusercontent.com/d/{logo_id}" if logo_id else ""

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
                        pin_actual = str(eq.get("PIN", "") or "—")
                        st.markdown(
                            f"<div style='font-size:12px;color:#666;line-height:2;'>"
                            f"<b style='color:#F5F0E8;'>Color primario:</b> "
                            f"<span style='background:{color};padding:2px 14px;"
                            f"border-radius:2px;'>&nbsp;</span> {color}<br>"
                            f"<b style='color:#F5F0E8;'>PIN actual:</b> "
                            f"<span style='font-family:DM Mono,monospace;color:#FFB800;'>"
                            f"{pin_actual}</span><br>"
                            f"<b style='color:#F5F0E8;'>Descripción:</b> "
                            f"{eq.get('Descripcion','—')}<br>"
                            f"<b style='color:#F5F0E8;'>Link tienda:</b> "
                            f"<span style='font-family:DM Mono,monospace;font-size:11px;'>"
                            f"?equipo={eq.get('Codigo','')}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        # Cambiar PIN
                        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                        nuevo_pin_input = st.text_input(
                            "Nuevo PIN (4-6 dígitos)", key=f"nuevo_pin_{eq['ID']}",
                            max_chars=6, placeholder="Ej: 5531"
                        )
                        if st.button("CAMBIAR PIN", key=f"btn_pin_{eq['ID']}"):
                            if not nuevo_pin_input or not nuevo_pin_input.isdigit() or not (4 <= len(nuevo_pin_input) <= 6):
                                st.error("El PIN debe ser numérico y tener entre 4 y 6 dígitos.")
                            else:
                                if actualizar_pin_equipo(client, eq["ID"], nuevo_pin_input):
                                    st.success(f"✅ PIN actualizado a `{nuevo_pin_input}`")
                                    st.rerun()
                        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
                        df_ped_eq = leer_pedidos(client)
                        ba, bb = st.columns(2)
                        with ba:
                            # Equipo activo (solo aparece en loop de activos)
                            if st.button("DESACTIVAR EQUIPO", key=f"deact_eq_{eq['ID']}"):
                                ws_eq = get_ws(client, HOJA_EQUIPOS)
                                cell_eq = ws_eq.find(eq["ID"]) if ws_eq else None
                                if cell_eq:
                                    ws_eq.update_cell(cell_eq.row, 9, "NO")
                                st.cache_data.clear()
                                st.rerun()
                        with bb:
                            if tiene_pedidos(df_ped_eq, "Equipo_ID", eq["ID"]):
                                st.markdown(
                                    "<div style='font-size:10px;color:#666;padding:8px 0;'>"
                                    "⚠️ Tiene pedidos — solo se puede desactivar</div>",
                                    unsafe_allow_html=True,
                                )
                            else:
                                if st.button("🗑 ELIMINAR DEFINITIVO", key=f"del_eq_{eq['ID']}"):
                                    st.session_state[f"confirm_eq_{eq['ID']}"] = True
                                if st.session_state.get(f"confirm_eq_{eq['ID']}"):
                                    st.warning("⚠️ Esto borra el equipo del Sheets. ¿Confirmar?")
                                    cy, cn = st.columns(2)
                                    with cy:
                                        if st.button("SÍ, ELIMINAR", key=f"yes_eq_{eq['ID']}"):
                                            # Buscar carpeta del equipo en Drive y eliminarla
                                            eq_folder_id = drive_get_equipo_folder(drive, eq["Nombre"])
                                            if eq_folder_id:
                                                drive_eliminar_carpeta(drive, eq_folder_id)
                                            eliminar_registro(client, HOJA_EQUIPOS, eq["ID"])
                                            st.session_state.pop(f"confirm_eq_{eq['ID']}", None)
                                            st.rerun()
                                    with cn:
                                        if st.button("CANCELAR", key=f"no_eq_{eq['ID']}"):
                                            st.session_state.pop(f"confirm_eq_{eq['ID']}", None)
                                            st.rerun()

            # ── Equipos archivados ─────────────────────────────────────────
            if not eq_inactivos.empty:
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                with st.expander(f"📁 ARCHIVADOS ({len(eq_inactivos)} equipos inactivos)"):
                    for _, eq in eq_inactivos.iterrows():
                        color = eq.get("Color_Primario", "#555") or "#555"
                        pin_actual = str(eq.get("PIN", "") or "—")
                        c1, c2, c3 = st.columns([3, 2, 1])
                        with c1:
                            st.markdown(
                                f"<div style='font-size:13px;color:#555;'>"
                                f"<b style='color:#777;'>{eq.get('Nombre','')}</b> · "
                                f"<span style='font-family:DM Mono,monospace;font-size:11px;'>"
                                f"{eq.get('Codigo','')}</span></div>"
                                f"<div style='font-size:11px;color:#444;'>PIN: {pin_actual}</div>",
                                unsafe_allow_html=True,
                            )
                        with c2:
                            st.markdown(
                                "<div style='font-size:11px;color:#444;padding:8px 0;'>"
                                "⚫ INACTIVO</div>",
                                unsafe_allow_html=True,
                            )
                        with c3:
                            if st.button("ACTIVAR", key=f"act_arch_{eq['ID']}"):
                                desactivar_registro(client, HOJA_EQUIPOS, eq["ID"], 9)
                                # Activo col 9 — pero necesitamos poner SI no NO
                                ws_eq = get_ws(client, HOJA_EQUIPOS)
                                cell_eq = ws_eq.find(eq["ID"]) if ws_eq else None
                                if cell_eq:
                                    ws_eq.update_cell(cell_eq.row, 9, "SI")
                                st.cache_data.clear()
                                st.rerun()
                        st.markdown("<hr style='border-color:#1a1a1a;margin:8px 0;'>",
                                    unsafe_allow_html=True)

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

            eq_pin     = st.text_input("PIN de acceso * (4-6 dígitos)", key="eq_pin",
                                       placeholder="Ej: 2847",
                                       max_chars=6)
            eq_desc    = st.text_area("Descripción / mensaje", key="eq_desc",
                                      placeholder="Bienvenido al portal de merch oficial de…")
            logo_nuevo = st.file_uploader("Logo del equipo (opcional)",
                                          type=["png", "jpg", "jpeg", "webp"],
                                          key="logo_nuevo")

            if st.button("CREAR EQUIPO", key="btn_crear_eq"):
                if not eq_nombre or not eq_codigo:
                    st.error("Nombre y código son obligatorios.")
                elif not eq_pin or not eq_pin.isdigit() or not (4 <= len(eq_pin) <= 6):
                    st.error("El PIN debe ser numérico y tener entre 4 y 6 dígitos.")
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
                            "pin": eq_pin.strip(),
                            "logo_drive_id": logo_id,
                            "color_primario": eq_color1,
                            "color_secundario": eq_color2,
                            "descripcion": eq_desc,
                        }
                        if guardar_equipo(client, nuevo):
                            st.success(f"✅ Equipo **{eq_nombre}** creado")
                            st.info(f"🔗 Link: `?equipo={eq_codigo.upper()}` · PIN: `{eq_pin}`")

    # ── TAB 2: COLECCIONES ────────────────────────────────────────────────────
    elif tab_activo == "colecciones":
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
                        # Eliminar colección
                        df_ped_col = leer_pedidos(client)
                        if tiene_pedidos(df_ped_col, "Coleccion_ID", col["ID"]):
                            st.markdown(
                                "<div style='font-size:10px;color:#555;margin-bottom:6px;'>"
                                "⚠️ Tiene pedidos — solo desactivar</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            if st.button("🗑 ELIMINAR", key=f"del_col_{col['ID']}"):
                                st.session_state[f"confirm_col_{col['ID']}"] = True
                            if st.session_state.get(f"confirm_col_{col['ID']}"):
                                st.warning(f"¿Eliminar **{col.get('Nombre','')}** definitivamente?")
                                cy, cn = st.columns(2)
                                with cy:
                                    if st.button("SÍ", key=f"yes_col_{col['ID']}"):
                                        # Buscar carpeta de la colección en Drive y eliminarla
                                        eq_row_col = df_eq[df_eq["ID"] == col.get("Equipo_ID","")]
                                        if not eq_row_col.empty:
                                            eq_nom_col = eq_row_col.iloc[0]["Nombre"]
                                            col_folder_id = drive_get_coleccion_folder(
                                                drive, eq_nom_col, col.get("Temporada","")
                                            )
                                            if col_folder_id:
                                                drive_eliminar_carpeta(drive, col_folder_id)
                                        eliminar_registro(client, HOJA_COLECCIONES, col["ID"])
                                        st.session_state.pop(f"confirm_col_{col['ID']}", None)
                                        st.rerun()
                                with cn:
                                    if st.button("NO", key=f"no_col_{col['ID']}"):
                                        st.session_state.pop(f"confirm_col_{col['ID']}", None)
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
                    col_corte_dt = st.date_input("Fecha de corte", value=None, key="col_corte")
                    col_corte = col_corte_dt.strftime("%d/%m/%Y") if col_corte_dt else ""

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
    elif tab_activo == "productos":
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
                    fotos_raw = str(p.get("Fotos_URLs", "") or "")
                    fotos = [(u.strip(), u.strip()) for u in fotos_raw.split(",") if u.strip()]

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
                            personalizable = p.get("Personalizable", "NO") == "SI"
                            st.markdown(
                                f"<div style='font-size:12px;color:#888;line-height:2;'>"
                                f"<b style='color:#F5F0E8;'>Tallas:</b> {p.get('Tallas','—')}<br>"
                                f"<b style='color:#F5F0E8;'>Colores:</b> {p.get('Colores','—')}<br>"
                                f"<b style='color:#F5F0E8;'>Personalizable:</b> "
                                f"<span style='color:{"#00C853" if personalizable else "#555"};'>"
                                f"{"✅ SÍ" if personalizable else "⚫ NO"}</span><br>"
                                f"<b style='color:#F5F0E8;'>Descripción:</b> "
                                f"{p.get('Descripcion','—')}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            # Toggle personalizable
                            lbl_pers = "QUITAR PERSONALIZABLE" if personalizable else "HACER PERSONALIZABLE"
                            if st.button(lbl_pers, key=f"pers_{p['ID']}"):
                                ws_p = get_ws(client, HOJA_PRODUCTOS)
                                cell_p = ws_p.find(p["ID"]) if ws_p else None
                                if cell_p:
                                    ws_p.update_cell(cell_p.row, 10, "NO" if personalizable else "SI")
                                    st.cache_data.clear()
                                    st.rerun()
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
                                        nuevas_urls = []
                                        for f_up in nuevas_fotos:
                                            _, url = drive_upload_file(
                                                drive, f_up.read(),
                                                f_up.name, f_up.type, folder_id,
                                            )
                                            nuevas_urls.append(url)
                                        # Acumular con las existentes en Sheets
                                        existentes = str(p.get("Fotos_URLs", "") or "")
                                        todas = [u for u in existentes.split(",") if u.strip()] + nuevas_urls
                                        actualizar_fotos_producto(client, p["ID"], ",".join(todas))
                                    st.success(f"✅ {len(nuevas_fotos)} foto(s) subidas")
                                    st.rerun()
                        # Acciones del producto
                        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                        df_ped_pro = leer_pedidos(client)
                        prod_activo = p.get("Activo", "SI") == "SI"
                        pa, pb, pc = st.columns(3)
                        with pa:
                            lbl_p = "DESACTIVAR" if prod_activo else "ACTIVAR"
                            if st.button(lbl_p, key=f"deact_p_{p['ID']}"):
                                desactivar_registro(client, HOJA_PRODUCTOS, p["ID"], 11)
                                st.rerun()
                        with pb:
                            if tiene_pedidos(df_ped_pro, "Productos_JSON", p["ID"]):
                                st.markdown(
                                    "<div style='font-size:10px;color:#555;padding:8px 0;'>"
                                    "⚠️ En pedidos — solo desactivar</div>",
                                    unsafe_allow_html=True,
                                )
                            else:
                                if st.button("🗑 ELIMINAR", key=f"del_p_{p['ID']}"):
                                    st.session_state[f"confirm_p_{p['ID']}"] = True
                                if st.session_state.get(f"confirm_p_{p['ID']}"):
                                    st.warning("¿Eliminar este producto definitivamente?")
                                    py, pn = st.columns(2)
                                    with py:
                                        if st.button("SÍ", key=f"yes_p_{p['ID']}"):
                                            folder_id = p.get("Drive_Folder_ID", "")
                                            if folder_id:
                                                drive_eliminar_carpeta(drive, folder_id)
                                            eliminar_registro(client, HOJA_PRODUCTOS, p["ID"])
                                            st.session_state.pop(f"confirm_p_{p['ID']}", None)
                                            st.rerun()
                                    with pn:
                                        if st.button("NO", key=f"no_p_{p['ID']}"):
                                            st.session_state.pop(f"confirm_p_{p['ID']}", None)
                                            st.rerun()
                        with pc:
                            estado_txt = "🟢 ACTIVO" if prod_activo else "⚫ INACTIVO"
                            color_est  = "#00C853" if prod_activo else "#555"
                            st.markdown(
                                f"<div style='font-size:11px;color:{color_est};"
                                f"padding:8px 0;'>{estado_txt}</div>",
                                unsafe_allow_html=True,
                            )

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
                        # Tallas una a una
                        if "tallas_lista" not in st.session_state:
                            st.session_state.tallas_lista = []
                        t_input = st.text_input("Agregar talla", key="prod_talla_input",
                                                placeholder="Ej: XS, S, M, 36, 38…")
                        if st.button("+ AGREGAR", key="btn_add_talla"):
                            t_val = t_input.strip().upper()
                            if t_val and t_val not in st.session_state.tallas_lista:
                                st.session_state.tallas_lista.append(t_val)
                                st.rerun()
                        if st.session_state.tallas_lista:
                            tallas_html = " ".join([
                                f"<span style='background:#222;color:#F5F0E8;font-size:11px;"
                                f"padding:3px 10px;border-radius:2px;margin-right:4px;"
                                f"font-family:DM Mono,monospace;'>{t}</span>"
                                for t in st.session_state.tallas_lista
                            ])
                            st.markdown(tallas_html, unsafe_allow_html=True)
                            if st.button("✕ LIMPIAR TALLAS", key="btn_clear_tallas"):
                                st.session_state.tallas_lista = []
                                st.rerun()
                        prod_tallas = ",".join(st.session_state.tallas_lista)
                    with c2:
                        st.markdown(
                            "<div style='font-size:12px;color:#444;padding:8px 0;'>"
                            "🎨 Colores — deshabilitado temporalmente</div>",
                            unsafe_allow_html=True,
                        )
                        prod_colores = ""
                        prod_desc    = st.text_area("Descripción", key="prod_desc",
                                                    placeholder="Material, detalles del diseño…")

                    prod_personalizable = st.checkbox(
                        "¿Producto personalizable? (el usuario puede poner su nombre)",
                        key="prod_personalizable"
                    )

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
                                fotos_urls_list = []
                                if prod_fotos:
                                    for f_up in prod_fotos:
                                        _, url = drive_upload_file(
                                            drive, f_up.read(),
                                            f_up.name, f_up.type, folder_id,
                                        )
                                        fotos_urls_list.append(url)
                                nuevo = {
                                    "id": prod_id, "coleccion_id": col_id_sel,
                                    "nombre": prod_nombre, "descripcion": prod_desc,
                                    "precio": prod_precio, "tallas": prod_tallas,
                                    "colores": prod_colores, "drive_folder_id": folder_id,
                                    "fotos_urls": ",".join(fotos_urls_list),
                                    "personalizable": "SI" if prod_personalizable else "NO",
                                }
                                if guardar_producto(client, nuevo):
                                    n = len(prod_fotos) if prod_fotos else 0
                                    st.session_state.tallas_lista = []
                                    st.success(f"✅ **{prod_nombre}** agregado con {n} foto(s)")

    # ── TAB 4: PEDIDOS ────────────────────────────────────────────────────────
    elif tab_activo == "pedidos":
        df_ped = leer_pedidos(client)
        df_col_ped = leer_colecciones(client)
        seccion("PEDIDOS", f"{len(df_ped)} pedidos registrados")

        if df_ped.empty:
            st.info("Aún no hay pedidos.")
        else:
            # ── Métricas ──────────────────────────────────────────────────────
            pagados    = len(df_ped[df_ped["Estado"] == "PAGADO"])
            pendientes = len(df_ped[df_ped["Estado"] == "PENDIENTE"])
            total_cop  = df_ped["Total"].apply(
                lambda x: float(str(x).replace(",", "")) if x else 0
            ).sum()
            total_pag  = df_ped[df_ped["Estado"] == "PAGADO"]["Total"].apply(
                lambda x: float(str(x).replace(",", "")) if x else 0
            ).sum()

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1: st.metric("Total pedidos", len(df_ped))
            with c2: st.metric("Pagados",       pagados)
            with c3: st.metric("Pendientes",    pendientes)
            with c4: st.metric("Valor total",   fmt_precio(total_cop))
            with c5: st.metric("Cobrado",       fmt_precio(total_pag))

            # ── Sincronizar pagos ─────────────────────────────────────────────
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            sc1, sc2 = st.columns([2, 3])
            with sc1:
                if st.button("🔄 SINCRONIZAR PAGOS CON SHOPIFY", key="btn_sync"):
                    with st.spinner("Consultando Shopify…"):
                        act, errs = sincronizar_pagos(client)
                    if act > 0:
                        st.success(f"✅ {act} pedido(s) marcados como PAGADO")
                    else:
                        st.info("Sin cambios — ningún pedido pendiente fue completado aún.")
                    if errs:
                        for e in errs:
                            st.warning(e)
            with sc2:
                st.markdown(
                    "<div style='font-size:11px;color:#555;padding:10px 0;'>"
                    "Consulta Shopify por cada Draft Order pendiente y actualiza "
                    "automáticamente los que ya fueron pagados.</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("<hr style='border-color:#1a1a1a;margin:16px 0;'>",
                        unsafe_allow_html=True)

            # ── Filtros ───────────────────────────────────────────────────────
            seccion("FILTROS Y REPORTE DE PRODUCCIÓN", "")
            f1, f2, f3 = st.columns(3)
            with f1:
                equipos_list = ["Todos"] + sorted(df_ped["Equipo_Nombre"].dropna().unique().tolist())
                filtro_eq = st.selectbox("Equipo:", equipos_list, key="filtro_eq_ped")
            with f2:
                cols_list = ["Todas"] + sorted(df_ped["Coleccion_Nombre"].dropna().unique().tolist())
                filtro_col = st.selectbox("Colección:", cols_list, key="filtro_col_ped")
            with f3:
                estados    = ["Todos", "PENDIENTE", "PAGADO", "PRODUCCION", "ENVIADO"]
                filtro_est = st.selectbox("Estado:", estados, key="filtro_est_ped")

            f4, f5 = st.columns(2)
            with f4:
                fecha_desde = st.date_input("Desde", value=None, key="fecha_desde_ped")
            with f5:
                fecha_hasta = st.date_input("Hasta", value=None, key="fecha_hasta_ped")

            df_show = df_ped.copy()
            if filtro_eq  != "Todos": df_show = df_show[df_show["Equipo_Nombre"] == filtro_eq]
            if filtro_col != "Todas": df_show = df_show[df_show["Coleccion_Nombre"] == filtro_col]
            if filtro_est != "Todos": df_show = df_show[df_show["Estado"] == filtro_est]
            if fecha_desde:
                df_show = df_show[pd.to_datetime(df_show["Fecha"], errors="coerce").dt.date >= fecha_desde]
            if fecha_hasta:
                df_show = df_show[pd.to_datetime(df_show["Fecha"], errors="coerce").dt.date <= fecha_hasta]

            df_show = df_show.sort_values("Fecha", ascending=False)

            st.markdown(
                f"<div style='font-size:11px;color:#666;margin-bottom:12px;'>"
                f"{len(df_show)} pedidos en la selección · "
                f"Total: <b style='color:#F5F0E8;'>{fmt_precio(df_show['Total'].apply(lambda x: float(str(x).replace(',','')) if x else 0).sum())}</b>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Lista de pedidos ──────────────────────────────────────────────
            for _, p in df_show.iterrows():
                estado = p.get("Estado", "PENDIENTE")
                color_estado = {
                    "PAGADO": "#00C853", "PENDIENTE": "#FFB800",
                    "PRODUCCION": "#4488FF", "ENVIADO": "#2D6A4F",
                }.get(estado, "#666")

                try:
                    prods = json.loads(p.get("Productos_JSON", "[]"))
                    prods_str = " · ".join([
                        f"{pr['nombre']} T:{pr.get('talla','')} x{pr['cantidad']}"
                        + (f" [{pr['nombre_camiseta']}]" if pr.get('nombre_camiseta') else "")
                        for pr in prods
                    ])
                except:
                    prods_str = str(p.get("Productos_JSON", ""))

                st.markdown(
                    f"<div style='background:#111;border:1px solid #222;border-radius:6px;"
                    f"padding:14px 18px;margin-bottom:6px;'>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;margin-bottom:4px;'>"
                    f"<div><span style='font-weight:600;'>{p.get('Usuario_Nombre','—')}</span>"
                    f"<span style='color:#555;font-size:12px;margin-left:10px;'>"
                    f"{p.get('Usuario_Email','')}</span></div>"
                    f"<div style='display:flex;gap:10px;align-items:center;'>"
                    f"<span style='font-family:Bebas Neue,sans-serif;font-size:18px;'>"
                    f"{fmt_precio(p.get('Total',0))}</span>"
                    f"<span style='background:{color_estado}22;color:{color_estado};"
                    f"font-size:9px;letter-spacing:1.5px;padding:3px 8px;border-radius:2px;"
                    f"font-family:DM Mono,monospace;'>{estado}</span>"
                    f"</div></div>"
                    f"<div style='font-size:11px;color:#666;'>"
                    f"{p.get('Equipo_Nombre','—')} · {p.get('Coleccion_Nombre','—')} · "
                    f"{p.get('Fecha','—')} · ID: {p.get('ID','—')}</div>"
                    f"<div style='font-size:11px;color:#555;margin-top:3px;'>{prods_str}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # ── Reporte de producción ─────────────────────────────────────────
            st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
            seccion("EXPORTAR REPORTE DE PRODUCCIÓN", "")

            if st.button("📥 GENERAR REPORTE", key="btn_export"):
                # Expandir productos: una fila por producto por pedido
                filas = []
                for _, p in df_show.iterrows():
                    try:
                        prods = json.loads(p.get("Productos_JSON", "[]"))
                    except:
                        prods = []
                    if not prods:
                        prods = [{}]
                    for pr in prods:
                        filas.append({
                            "Fecha":             p.get("Fecha", ""),
                            "Pedido_ID":         p.get("ID", ""),
                            "Equipo":            p.get("Equipo_Nombre", ""),
                            "Coleccion":         p.get("Coleccion_Nombre", ""),
                            "Usuario_Nombre":    p.get("Usuario_Nombre", ""),
                            "Usuario_Email":     p.get("Usuario_Email", ""),
                            "Producto":          pr.get("nombre", ""),
                            "Talla":             pr.get("talla", ""),
                            "Cantidad":          pr.get("cantidad", ""),
                            "Nombre_Camiseta":   pr.get("nombre_camiseta", ""),
                            "Precio_Unitario":   pr.get("precio", ""),
                            "Subtotal":          float(str(pr.get("precio",0))) * int(pr.get("cantidad",1)) if pr.get("precio") and pr.get("cantidad") else "",
                            "Total_Pedido":      p.get("Total", ""),
                            "Estado":            p.get("Estado", ""),
                            "Shopify_Order_ID":  p.get("Shopify_Order_ID", ""),
                            "Shopify_Draft_ID":  p.get("Shopify_Draft_ID", ""),
                        })

                df_reporte = pd.DataFrame(filas)
                csv = df_reporte.to_csv(index=False).encode("utf-8")
                eq_label  = filtro_eq.replace(" ", "_") if filtro_eq != "Todos" else "todos"
                col_label = filtro_col.replace(" ", "_") if filtro_col != "Todas" else "todas"
                fname = f"reporte_produccion_{eq_label}_{col_label}_{datetime.now().strftime('%Y%m%d')}.csv"
                st.download_button(
                    "⬇️ Descargar CSV de producción",
                    csv,
                    fname,
                    "text/csv",
                    key="dl_csv",
                )
                st.markdown(
                    f"<div style='font-size:12px;color:#666;margin-top:8px;'>"
                    f"{len(filas)} filas · {len(df_show)} pedidos · "
                    f"Filtro: {filtro_eq} / {filtro_col} / {filtro_est}"
                    f"</div>",
                    unsafe_allow_html=True,
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
    logo_url  = f"https://lh3.googleusercontent.com/d/{logo_id}" if logo_id else ""
    eq_pin    = str(eq.get("PIN", "") or "")

    # ── Verificación de PIN ────────────────────────────────────────────────────
    session_key = f"pin_ok_{eq_id}"
    if eq_pin and not st.session_state.get(session_key):
        logo_html_pin = (
            f"<img src='{logo_url}' style='height:48px;object-fit:contain;"
            f"margin-bottom:12px;border-radius:4px;'>"
            if logo_url else ""
        )
        st.markdown(
            f"<div style='max-width:360px;margin:60px auto;text-align:center;'>"
            f"<div style='margin-bottom:32px;'>{LOGO_SVG}</div>"
            f"<div style='width:64px;height:1px;background:#222;margin:0 auto 24px;'></div>"
            f"{logo_html_pin}"
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:32px;"
            f"letter-spacing:5px;color:{eq_color};margin-bottom:4px;line-height:1;'>"
            f"{eq_nombre.upper()}</div>"
            f"<div style='font-size:10px;color:#444;letter-spacing:3px;"
            f"margin-bottom:36px;font-family:DM Mono,monospace;'>COLECCIÓN EXCLUSIVA</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        _, col_pin, _ = st.columns([1, 2, 1])
        with col_pin:
            pin_input = st.text_input(
                "Ingresa el PIN de acceso", type="password",
                key=f"pin_input_{eq_id}", max_chars=6,
                placeholder="PIN numérico",
            )
            if st.button("ACCEDER", key=f"btn_pin_acceder_{eq_id}"):
                if pin_input.strip() == eq_pin.strip():
                    st.session_state[session_key] = True
                    st.rerun()
                else:
                    st.error("PIN incorrecto. Verifica con tu coach.")
        st.stop()

    cols_activas = df_col[
        (df_col["Equipo_ID"] == eq_id) & (df_col["Activa"] == "SI")
    ]

    # Header
    # Nav bar tienda
    st.markdown(
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"padding:16px 0 16px 0;border-bottom:1px solid #1E1E1E;margin-bottom:32px;'>"
        f"<a href='https://terret.co' target='_blank' style='text-decoration:none;'>"
        f"{LOGO_SVG}</a>"
        f"<div style='font-size:10px;color:#444;letter-spacing:2px;"
        f"font-family:DM Mono,monospace;'>COLECCIÓN EXCLUSIVA</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Hero del equipo
    logo_html = (
        f"<img src='{logo_url}' style='height:56px;object-fit:contain;"
        f"margin-right:20px;'>"
        if logo_url else ""
    )
    st.markdown(
        f"<div style='display:flex;align-items:center;margin-bottom:8px;'>"
        f"{logo_html}"
        f"<div>"
        f"<div style='font-family:Bebas Neue,sans-serif;font-size:40px;"
        f"letter-spacing:5px;color:{eq_color};line-height:1;'>{eq_nombre.upper()}</div>"
        f"<div style='font-size:11px;color:#555;letter-spacing:2px;"
        f"font-family:DM Mono,monospace;margin-top:4px;'>MERCH PERSONALIZADO</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    if eq_desc:
        st.markdown(
            f"<div style='color:#888;font-size:14px;margin-bottom:20px;'>{eq_desc}</div>",
            unsafe_allow_html=True,
        )

    # ── Recuperar pedido pendiente ─────────────────────────────────────────────
    with st.expander("¿Ya hiciste un pedido y perdiste el link de pago?"):
        email_rec = st.text_input("Ingresa tu correo electrónico", key="email_recuperar",
                                  placeholder="El correo que usaste al hacer el pedido")
        if st.button("BUSCAR MI PEDIDO", key="btn_recuperar"):
            if not email_rec or "@" not in email_rec:
                st.error("Ingresa un correo válido.")
            else:
                df_ped_rec = leer_pedidos(client)
                pedidos_rec = df_ped_rec[
                    (df_ped_rec["Usuario_Email"].str.lower() == email_rec.lower().strip()) &
                    (df_ped_rec["Equipo_ID"] == eq_id) &
                    (df_ped_rec["Estado"] == "PENDIENTE")
                ] if not df_ped_rec.empty else pd.DataFrame()

                if pedidos_rec.empty:
                    st.info("No encontramos pedidos pendientes con ese correo para este equipo.")
                else:
                    for _, ped_rec in pedidos_rec.sort_values("Fecha", ascending=False).iterrows():
                        inv_url = ped_rec.get("Invoice_URL", "")
                        if inv_url:
                            st.markdown(
                                f"<div style='background:#0a1a0a;border:1px solid #1a3a1a;"
                                f"border-radius:6px;padding:16px;margin-bottom:8px;'>"
                                f"<div style='font-size:13px;margin-bottom:8px;'>"
                                f"Pedido <b style='color:#F5F0E8;'>{ped_rec.get('ID','')}</b> · "
                                f"{ped_rec.get('Fecha','')} · "
                                f"<b style='color:#F5F0E8;'>{fmt_precio(ped_rec.get('Total',0))}</b>"
                                f"</div>"
                                f"<a href='{inv_url}' target='_blank' "
                                f"style='background:#00C853;color:#0A0A0A;"
                                f"font-family:Bebas Neue,sans-serif;font-size:14px;"
                                f"letter-spacing:2px;padding:8px 20px;border-radius:3px;"
                                f"text-decoration:none;display:inline-block;'>"
                                f"IR AL PAGO →</a></div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.info(f"Pedido {ped_rec.get('ID','')} encontrado pero sin link de pago. Contacta a Térret.")

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

    # ── SIDEBAR + FLUJO MULTISTEP ────────────────────────────────────────────
    # Steps: "shop" → "checkout" → "confirmed"
    if "shop_step" not in st.session_state:
        st.session_state.shop_step = "shop"

    with st.sidebar:
        st.markdown(
            f"<div style='padding:8px 0 20px 0;border-bottom:1px solid #1A1A1A;"
            f"margin-bottom:20px;'>{LOGO_SVG}</div>",
            unsafe_allow_html=True,
        )

        n_items = sum(item["cantidad"] for item in st.session_state.carrito)
        total_sb = sum(item["precio"] * item["cantidad"] for item in st.session_state.carrito)

        if not st.session_state.carrito:
            st.markdown(
                "<div style='font-size:9px;color:#333;letter-spacing:3px;"
                "margin-bottom:16px;'>CARRITO</div>"
                "<div style='font-size:12px;color:#333;padding:8px 0;'>"
                "Agrega productos para continuar.</div>",
                unsafe_allow_html=True,
            )
        else:
            step = st.session_state.shop_step

            if step == "shop":
                # ── Step 1: resumen carrito + botón IR AL PAGO ────────────────
                st.markdown(
                    f"<div style='font-size:9px;color:#888;letter-spacing:3px;"
                    f"margin-bottom:12px;'>CARRITO ({n_items})</div>",
                    unsafe_allow_html=True,
                )
                for idx, item in enumerate(st.session_state.carrito):
                    subtotal = item["precio"] * item["cantidad"]
                    nombre_cam = f" · {item['nombre_camiseta']}" if item.get("nombre_camiseta") else ""
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(
                            f"<div style='padding:8px 0;border-bottom:1px solid #1A1A1A;'>"
                            f"<div style='font-size:12px;color:#FFF;font-weight:500;'>{item['nombre']}</div>"
                            f"<div style='font-size:10px;color:#555;margin-top:2px;'>"
                            f"T:{item['talla']} · x{item['cantidad']}{nombre_cam}</div>"
                            f"<div style='font-size:13px;font-family:Bebas Neue,sans-serif;"
                            f"color:{eq_color};margin-top:4px;'>{fmt_precio(subtotal)}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        if st.button("✕", key=f"rm_sb_{idx}"):
                            st.session_state.carrito.pop(idx)
                            st.rerun()

                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;padding:14px 0 20px 0;'>"
                    f"<span style='font-size:9px;color:#555;letter-spacing:2px;'>TOTAL</span>"
                    f"<span style='font-family:Bebas Neue,sans-serif;font-size:22px;"
                    f"color:{eq_color};'>{fmt_precio(total_sb)}</span></div>",
                    unsafe_allow_html=True,
                )
                if st.button("IR AL PAGO →", key="btn_ir_pago"):
                    st.session_state.shop_step = "checkout"
                    st.rerun()
                if st.button("VACIAR", key="vaciar_sb"):
                    st.session_state.carrito = []
                    st.rerun()

            elif step == "checkout":
                # ── Step 2: datos del usuario (solo en sidebar) ───────────────
                st.markdown(
                    "<div style='font-size:9px;color:#888;letter-spacing:3px;"
                    "margin-bottom:4px;'>PASO 2 DE 2</div>"
                    "<div style='font-size:14px;color:#FFF;font-weight:600;"
                    "margin-bottom:16px;'>Tus datos</div>",
                    unsafe_allow_html=True,
                )
                # Resumen compacto
                st.markdown(
                    f"<div style='background:#111;border-radius:3px;padding:10px 12px;"
                    f"margin-bottom:16px;'>"
                    f"<div style='font-size:10px;color:#555;'>{n_items} producto(s)</div>"
                    f"<div style='font-family:Bebas Neue,sans-serif;font-size:18px;"
                    f"color:{eq_color};'>{fmt_precio(total_sb)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                nombre = st.text_input("Nombre completo *", key="buyer_nombre",
                                       placeholder="Tu nombre completo")
                email  = st.text_input("Correo electrónico *", key="buyer_email",
                                       placeholder="tu@correo.com")
                notas  = st.text_area("Notas (opcional)", key="buyer_notas",
                                      placeholder="Dirección de envío, etc.", height=70)

                if st.button("CONFIRMAR Y PAGAR →", key="btn_pagar"):
                    if not nombre or not email:
                        st.error("Nombre y correo son obligatorios.")
                    elif "@" not in email:
                        st.error("Correo inválido.")
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
                            st.error(f"Error: {err}")
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
                                "total":            total_sb,
                                "shopify_draft_id": draft["id"],
                                "invoice_url":      draft.get("invoice_url", ""),
                                "notas":            notas,
                            }
                            guardar_pedido(client, pedido_data)
                            checkout_url = draft.get("invoice_url", "")
                            if checkout_url:
                                st.session_state.carrito    = []
                                st.session_state.shop_step  = "confirmed"
                                st.session_state["checkout_url"] = checkout_url
                                st.session_state["pedido_id"]    = pedido_id
                                st.rerun()
                            else:
                                st.warning("Pedido registrado sin link de pago. Contacta a Térret.")

                if st.button("← VOLVER AL CARRITO", key="btn_volver"):
                    st.session_state.shop_step = "shop"
                    st.rerun()

        # Footer sidebar
        st.markdown("<div style='height:1px;background:#1A1A1A;margin:20px 0;'></div>",
                    unsafe_allow_html=True)
        st.markdown(
            "<a href='https://terret.co' target='_blank' "
            "style='font-size:10px;color:#333;letter-spacing:1px;"
            "text-decoration:none;'>terret.co ↗</a>",
            unsafe_allow_html=True,
        )

    # ── CONTENIDO PRINCIPAL según step ────────────────────────────────────────
    step = st.session_state.get("shop_step", "shop")

    if step == "confirmed":
        # Pantalla de confirmación centrada
        checkout_url = st.session_state.get("checkout_url", "")
        pedido_id_conf = st.session_state.get("pedido_id", "")
        st.markdown(
            f"<div style='max-width:560px;margin:80px auto;text-align:center;'>"
            f"<div style='font-size:48px;margin-bottom:16px;'>✅</div>"
            f"<div style='font-family:Bebas Neue,sans-serif;font-size:28px;"
            f"letter-spacing:4px;color:#FFF;margin-bottom:8px;'>PEDIDO REGISTRADO</div>"
            f"<div style='font-size:11px;color:#555;letter-spacing:2px;"
            f"margin-bottom:32px;font-family:DM Mono,monospace;'>{pedido_id_conf}</div>"
            f"<div style='color:#555;font-size:13px;line-height:1.9;margin-bottom:32px;'>"
            f"Tu pedido quedó registrado.<br>"
            f"Completa el pago en Shopify para confirmar tu compra.</div>"
            f"<a href='{checkout_url}' target='_blank' "
            f"style='display:inline-block;background:#FFFFFF;color:#0A0A0A;"
            f"font-family:Bebas Neue,sans-serif;font-size:14px;"
            f"letter-spacing:3px;padding:16px 48px;border-radius:2px;"
            f"text-decoration:none;margin-bottom:24px;'>PAGAR AHORA →</a>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("← SEGUIR COMPRANDO", key="btn_seguir"):
            del st.session_state["checkout_url"]
            del st.session_state["pedido_id"]
            st.session_state.shop_step = "shop"
            st.rerun()

    elif step == "checkout":
        # Pantalla de checkout: resumen visual del pedido
        seccion("TU PEDIDO", "Revisa antes de pagar")
        total_ch = 0
        for item in st.session_state.get("carrito_snapshot", st.session_state.carrito):
            subtotal = item["precio"] * item["cantidad"]
            total_ch += subtotal
            nombre_cam = f" · Nombre: **{item['nombre_camiseta']}**" if item.get("nombre_camiseta") else ""
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:center;padding:12px 0;border-bottom:1px solid #1A1A1A;'>"
                f"<div>"
                f"<div style='font-size:13px;color:#FFF;font-weight:500;'>{item['nombre']}</div>"
                f"<div style='font-size:11px;color:#555;margin-top:2px;'>"
                f"Talla: {item['talla']} · Cantidad: {item['cantidad']}{nombre_cam}</div>"
                f"</div>"
                f"<div style='font-family:Bebas Neue,sans-serif;font-size:18px;"
                f"color:{eq_color};'>{fmt_precio(subtotal)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:20px 0;margin-top:8px;'>"
            f"<span style='font-size:10px;color:#444;letter-spacing:3px;'>TOTAL</span>"
            f"<span style='font-family:Bebas Neue,sans-serif;font-size:32px;"
            f"color:{eq_color};'>{fmt_precio(total_ch)}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.info("👈 Completa tus datos en el panel izquierdo y haz clic en **CONFIRMAR Y PAGAR →**")

    else:
        # Step "shop" — grid de productos
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

            # Countdown dinámico en JS
            if col_corte:
                # Parsear la fecha de corte (formato DD/MM/YYYY)
                try:
                    partes = col_corte.strip().split("/")
                    if len(partes) == 3:
                        fecha_iso = f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}T23:59:59"
                    else:
                        fecha_iso = col_corte
                except:
                    fecha_iso = col_corte
                countdown_id = f"cd_{col_id.replace('-','')}"
                corte_html = (
                    f"<div style='margin-top:12px;margin-bottom:4px;'>"
                    f"<div style='font-size:9px;color:#555;letter-spacing:2px;"
                    f"margin-bottom:8px;font-family:DM Mono,monospace;'>CIERRE DE PEDIDOS</div>"
                    f"<div id='{countdown_id}' style='display:flex;gap:12px;align-items:flex-end;'>"
                    f"<div style='text-align:center;'>"
                    f"<div id='{countdown_id}_d' style='font-family:Bebas Neue,sans-serif;"
                    f"font-size:32px;color:#FFB800;line-height:1;'>--</div>"
                    f"<div style='font-size:8px;color:#555;letter-spacing:2px;margin-top:2px;'>DÍAS</div></div>"
                    f"<div style='font-size:20px;color:#333;padding-bottom:6px;'>:</div>"
                    f"<div style='text-align:center;'>"
                    f"<div id='{countdown_id}_h' style='font-family:Bebas Neue,sans-serif;"
                    f"font-size:32px;color:#FFB800;line-height:1;'>--</div>"
                    f"<div style='font-size:8px;color:#555;letter-spacing:2px;margin-top:2px;'>HRS</div></div>"
                    f"<div style='font-size:20px;color:#333;padding-bottom:6px;'>:</div>"
                    f"<div style='text-align:center;'>"
                    f"<div id='{countdown_id}_m' style='font-family:Bebas Neue,sans-serif;"
                    f"font-size:32px;color:#FFB800;line-height:1;'>--</div>"
                    f"<div style='font-size:8px;color:#555;letter-spacing:2px;margin-top:2px;'>MIN</div></div>"
                    f"<div style='font-size:20px;color:#333;padding-bottom:6px;'>:</div>"
                    f"<div style='text-align:center;'>"
                    f"<div id='{countdown_id}_s' style='font-family:Bebas Neue,sans-serif;"
                    f"font-size:32px;color:#FFB800;line-height:1;'>--</div>"
                    f"<div style='font-size:8px;color:#555;letter-spacing:2px;margin-top:2px;'>SEG</div></div>"
                    f"</div>"
                    f"<script>"
                    f"(function(){{"
                    f"var target = new Date('{fecha_iso}').getTime();"
                    f"function tick(){{"
                    f"var now = new Date().getTime();"
                    f"var diff = target - now;"
                    f"if(diff <= 0){{"
                    f"document.getElementById('{countdown_id}_d').innerText='00';"
                    f"document.getElementById('{countdown_id}_h').innerText='00';"
                    f"document.getElementById('{countdown_id}_m').innerText='00';"
                    f"document.getElementById('{countdown_id}_s').innerText='00';"
                    f"return;}}"
                    f"var d=Math.floor(diff/86400000);"
                    f"var h=Math.floor((diff%86400000)/3600000);"
                    f"var m=Math.floor((diff%3600000)/60000);"
                    f"var s=Math.floor((diff%60000)/1000);"
                    f"document.getElementById('{countdown_id}_d').innerText=String(d).padStart(2,'0');"
                    f"document.getElementById('{countdown_id}_h').innerText=String(h).padStart(2,'0');"
                    f"document.getElementById('{countdown_id}_m').innerText=String(m).padStart(2,'0');"
                    f"document.getElementById('{countdown_id}_s').innerText=String(s).padStart(2,'0');"
                    f"}}"
                    f"tick(); setInterval(tick, 1000);"
                    f"}})();"
                    f"</script>"
                    f"</div>"
                )
            else:
                corte_html = ""

            st.markdown(
                f"<div style='margin:40px 0 20px 0;padding-bottom:14px;"
                f"border-bottom:1px solid #1A1A1A;'>"
                f"<div style='font-family:Bebas Neue,sans-serif;font-size:16px;"
                f"letter-spacing:4px;color:{eq_color};'>{col_nombre.upper()}</div>"
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

            # Inicializar modal state
            if "modal_prod_id" not in st.session_state:
                st.session_state.modal_prod_id = None

            cols_grid = st.columns(4)
            for i, (_, prod) in enumerate(productos.iterrows()):
                with cols_grid[i % 4]:
                    precio    = float(str(prod.get("Precio", 0)).replace(",", "") or 0)
                    fotos_raw = str(prod.get("Fotos_URLs", "") or "")
                    fotos     = [u.strip() for u in fotos_raw.split(",") if u.strip()]
                    img_src   = fotos[0] if fotos else ""

                    img_html = (
                        f"<img src='{img_src}' style='width:100%;display:block;"
                        f"border-radius:4px 4px 0 0;'>"
                        if img_src else
                        f"<div style='width:100%;aspect-ratio:1/1;background:#1a1a1a;"
                        f"border-radius:4px 4px 0 0;display:flex;align-items:center;"
                        f"justify-content:center;color:#333;font-size:32px;'>👕</div>"
                    )
                    desc = str(prod.get("Descripcion", "") or "")
                    desc_short = desc[:60] + "…" if len(desc) > 60 else desc

                    st.markdown(
                        f"<div style='background:#0F0F0F;border:1px solid #1A1A1A;"
                        f"border-radius:3px;margin-bottom:4px;overflow:hidden;"
                        f"transition:border-color 0.2s;'>"
                        f"{img_html}"
                        f"<div style='padding:12px 14px 14px;'>"
                        f"<div style='font-size:13px;font-weight:500;color:#FFF;"
                        f"margin-bottom:3px;letter-spacing:0.3px;'>"
                        f"{prod.get('Nombre','')}</div>"
                        f"<div style='font-size:11px;color:#555;margin-bottom:10px;"
                        f"line-height:1.5;'>{desc_short}</div>"
                        f"<div style='font-family:Bebas Neue,sans-serif;font-size:20px;"
                        f"color:{eq_color};letter-spacing:1px;'>{fmt_precio(precio)}</div>"
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )
                    if st.button("VER PRODUCTO", key=f"open_{prod['ID']}"):
                        st.session_state.modal_prod_id = prod["ID"]
                        st.rerun()

            # ── Modal de producto con st.dialog ───────────────────────────────────
            if st.session_state.get("modal_prod_id"):
                prod_modal = productos[productos["ID"] == st.session_state.modal_prod_id]
                if not prod_modal.empty:
                    prod_data = prod_modal.iloc[0]

                    @st.dialog(prod_data.get("Nombre", "Producto"), width="large")
                    def mostrar_modal_producto():
                        prod      = prod_data
                        precio    = float(str(prod.get("Precio", 0)).replace(",", "") or 0)
                        tallas    = [t.strip() for t in str(prod.get("Tallas", "")).split(",") if t.strip()]
                        fotos_raw = str(prod.get("Fotos_URLs", "") or "")
                        fotos     = [u.strip() for u in fotos_raw.split(",") if u.strip()]
                        desc      = str(prod.get("Descripcion", "") or "")
                        es_personalizable = str(prod.get("Personalizable", "NO")).upper() == "SI"
                        prod_key  = f"modal_{prod['ID']}"

                        st.markdown(
                            f"<div style='font-family:Bebas Neue,sans-serif;font-size:28px;"
                            f"color:{eq_color};margin-bottom:4px;'>{fmt_precio(precio)}</div>",
                            unsafe_allow_html=True,
                        )

                        mc1, mc2 = st.columns([1, 1])
                        with mc1:
                            if fotos:
                                st.image(fotos[0], use_container_width=True)
                                if len(fotos) > 1:
                                    for foto_extra in fotos[1:]:
                                        st.image(foto_extra, use_container_width=True)
                            else:
                                st.markdown(
                                    "<div style='height:280px;background:#1a1a1a;"
                                    "border-radius:4px;display:flex;align-items:center;"
                                    "justify-content:center;color:#333;font-size:40px;'>👕</div>",
                                    unsafe_allow_html=True,
                                )
                        with mc2:
                            if desc:
                                st.markdown(
                                    f"<div style='color:#888;font-size:13px;"
                                    f"margin-bottom:20px;line-height:1.7;'>{desc}</div>",
                                    unsafe_allow_html=True,
                                )

                            # Tallas desplegable
                            talla_sel = st.selectbox(
                                "Talla", tallas, key=f"talla_sel_{prod['ID']}"
                            ) if tallas else ""

                            cant = st.number_input("Cantidad", min_value=1, max_value=20,
                                                   value=1, key=f"cant_{prod_key}")

                            nombre_camiseta = ""
                            if es_personalizable:
                                nombre_camiseta = st.text_input(
                                    "Nombre en la camiseta (opcional, máx. 20 caracteres)",
                                    max_chars=20, key=f"nombre_cam_{prod_key}",
                                    placeholder="Ej: CARLOS",
                                )

                            if st.button("🛒 AGREGAR AL CARRITO", key=f"add_{prod_key}",
                                         use_container_width=True):
                                st.session_state.carrito.append({
                                    "prod_id":          prod["ID"],
                                    "nombre":           prod["Nombre"],
                                    "precio":           precio,
                                    "talla":            talla_sel,
                                    "color":            "",
                                    "cantidad":         int(cant),
                                    "coleccion_id":     col_id,
                                    "coleccion_nombre": col_nombre,
                                    "nombre_camiseta":  nombre_camiseta.strip().upper() if nombre_camiseta else "",
                                })
                                st.session_state.modal_prod_id = None
                                st.rerun()

                    mostrar_modal_producto()


    # Footer tienda
    st.markdown(
        f"<div style='border-top:1px solid #1E1E1E;margin-top:64px;padding:32px 0;"
        f"text-align:center;'>"
        f"<div style='margin-bottom:16px;'>{LOGO_SVG}</div>"
        f"<div style='font-size:10px;color:#333;letter-spacing:2px;"
        f"font-family:DM Mono,monospace;'>"
        f"<a href='https://terret.co' target='_blank' "
        f"style='color:#333;text-decoration:none;'>terret.co</a>"
        f" · MERCH PERSONALIZADO</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─── LOGIN ADMIN ──────────────────────────────────────────────────────────────
def login_admin():
    st.markdown(
        f"<div style='max-width:360px;margin:80px auto;text-align:center;'>"
        f"<div style='margin-bottom:40px;'>{LOGO_SVG}</div>"
        f"<div style='font-size:10px;color:#444;letter-spacing:3px;margin-bottom:40px;"
        f"font-family:DM Mono,monospace;'>PANEL DE ADMINISTRACIÓN</div>"
        f"</div>",
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
        "<a href='https://terret.co' style='color:#F5F0E8;'>terret.co</a>"
        "</div></div></div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

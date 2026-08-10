import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os

# -----------------------------------------------------------------------------
# 1. CONFIGURATION DE LA PAGE
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Plateforme Nationale de Surveillance Forestiere & Alerte Précoce (RDC)",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. INITIALISATION GOOGLE EARTH ENGINE (GEE)
# -----------------------------------------------------------------------------
@st.cache_resource
def init_gee():
    try:
        if "GEE_JSON" in st.secrets:
            secrets_data = st.secrets["GEE_JSON"]
            if isinstance(secrets_data, str):
                json_creds = json.loads(secrets_data)
            else:
                json_creds = dict(secrets_data)
                
            credentials = ee.ServiceAccountCredentials(
                json_creds["client_email"],
                key_data=json.dumps(json_creds)
            )
            ee.Initialize(credentials)
            return True, "Initialisation réussie via st.secrets."
        else:
            ee.Initialize()
            return True, "Initialisation réussie via authentification locale."
    except Exception as e:
        return False, str(e)

gee_ok, gee_msg = init_gee()

def add_ee_layer(ee_image_object, vis_params, name):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    return folium.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=name,
        overlay=True,
        control=True
    )

# -----------------------------------------------------------------------------
# 3. CHARGEMENT DU SHAPEFILE LOCAL (RDC / PROVINCES)
# -----------------------------------------------------------------------------
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SHP_PATH = os.path.join(WORK_DIR, "gadm41_COD_1.shp")

@st.cache_data
def load_shapefile(path):
    if os.path.exists(path):
        gdf = gpd.read_file(path)
        if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
        return gdf
    return None

gdf_provinces = load_shapefile(SHP_PATH)

# -----------------------------------------------------------------------------
# 4. BARRE LATÉRALE - NAVIGATION ET PARAMÈTRES
# -----------------------------------------------------------------------------
LOGO_PATH = os.path.join(WORK_DIR, "logo.png")
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.join(WORK_DIR, "logo.png.jpeg")

if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)

st.sidebar.title("⚙️ Paramètres de Navigation")

menu_option = st.sidebar.radio(
    "Navigation Fonctionnelle :",
    [
        "📊 Observatoire Spatiale",
        "🚨 Système d'Alerte Précoce (RADD/Sentinel)",
        "🔮 Modélisation Prospective & IA (2025-2035)",
        "📥 Rapports & Exportations"
    ]
)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Choix de la Zone d'Étude")

if gdf_provinces is not None and "NAME_1" in gdf_provinces.columns:
    provinces_list = sorted(gdf_provinces["NAME_1"].dropna().unique().tolist())
    select_options = ["🇨🇩 Toute la RDC (Vue Nationale)"] + provinces_list
    selected_option = st.sidebar.selectbox("Zone administrative :", select_options, index=select_options.index("Tshopo") if "Tshopo" in select_options else 0)
    
    if selected_option == "🇨🇩 Toute la RDC (Vue Nationale)":
        is_national = True
        current_prov = "Toute la RDC"
    else:
        is_national = False
        current_prov = selected_option
else:
    is_national = False
    current_prov = "Tshopo"

st.sidebar.markdown("---")
st.sidebar.subheader("📌 Vérification de Terrain (GPS)")
use_gps = st.sidebar.checkbox("Activer un point de contrôle GPS", value=False)

gps_lat, gps_lon = None, None
if use_gps:
    format_coord = st.sidebar.radio("Format des coordonnées GPS :", ["Degrés Décimaux (DD)", "Degrés Minutes Secondes (DMS)"])
    
    if format_coord == "Degrés Décimaux (DD)":
        gps_lat = st.sidebar.number_input("Latitude (°N/S) :", value=0.500000, format="%.6f")
        gps_lon = st.sidebar.number_input("Longitude (°E) :", value=25.200000, format="%.6f")
    else:
        c1, c2, c3, c4 = st.sidebar.columns(4)
        lat_d = c1.number_input("Deg (°)", value=0, key="lat_d")
        lat_m = c2.number_input("Min (')", value=30, key="lat_m")
        lat_s = c3.number_input("Sec (\")", value=0.0, key="lat_s")
        lat_dir = c4.selectbox("Hemi", ["N", "S"], key="lat_dir")
        
        c5, c6, c7, c8 = st.sidebar.columns(4)
        lon_d = c5.number_input("Deg (°)", value=25, key="lon_d")
        lon_m = c6.number_input("Min (')", value=12, key="lon_m")
        lon_s = c7.number_input("Sec (\")", value=0.0, key="lon_s")
        lon_dir = c8.selectbox("Hemi", ["E", "W"], key="lon_dir")
        
        gps_lat = (lat_d + (lat_m / 60.0) + (lat_s / 3600.0)) * (-1 if lat_dir == "S" else 1)
        gps_lon = (lon_d + (lon_m / 60.0) + (lon_s / 3600.0)) * (-1 if lon_dir == "W" else 1)

    gps_label = st.sidebar.text_input("Identifiant / Remarque :", value="Point de contrôle terrain")

btn_refresh = st.sidebar.button("🚀 Lancer / Actualiser L'Analyse", type="primary")

# -----------------------------------------------------------------------------
# 5. MOTEUR DE CALCUL EARTH ENGINE
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def compute_gee_stats(geo_json_str, scale=1000):
    try:
        region = ee.Geometry(json.loads(geo_json_str))
        hansen = ee.Image("UMD/hansen/global_forest_change_2023_v1_11").clip(region)
        treecover2000 = hansen.select('treecover2000')
        loss = hansen.select('loss')
        
        primary_forest = treecover2000.gte(60).And(loss.eq(0))
        secondary_forest = treecover2000.gte(10).And(treecover2000.lt(60)).And(loss.eq(0))
        deforestation = loss.gt(0)
        other_land = treecover2000.lt(10).And(loss.eq(0))
        
        pixel_area = ee.Image.pixelArea().divide(10000)
        def get_area(mask_img):
            stat = mask_img.multiply(pixel_area).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=region, scale=scale, maxPixels=1e13, bestEffort=True
            )
            val = stat.getInfo()
            if val:
                key = list(val.keys())[0]
                return float(val[key]) if val[key] is not None else 0.0
            return 0.0

        return {
            "success": True,
            "primary": get_area(primary_forest),
            "secondary": get_area(secondary_forest),
            "deforestation": get_area(deforestation),
            "other": get_area(other_land),
            "total": get_area(primary_forest) + get_area(secondary_forest) + get_area(deforestation) + get_area(other_land)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if gdf_provinces is not None:
    if is_national:
        selected_gdf, scale_res, zoom_lvl, map_center = gdf_provinces, 1000, 5, [-2.5, 23.5]
    else:
        selected_gdf = gdf_provinces[gdf_provinces['NAME_1'] == current_prov]
        scale_res, centroid = 150, selected_gdf.geometry.centroid.iloc[0]
        map_center, zoom_lvl = [centroid.y, centroid.x], 7
    geo_json_payload = selected_gdf.geometry.unary_union.__geo_interface__
else:
    map_center, zoom_lvl, scale_res, geo_json_payload = [0.5, 25.2], 7, 150, {"type": "Point", "coordinates": [25.2, 0.5]}

# -----------------------------------------------------------------------------
# 6. EN-TÊTE PRINCIPAL
# -----------------------------------------------------------------------------
st.title("🌲 Plateforme Nationale de Surveillance Forestiere, Prospective & Alerte Précoce (RDC)")
st.caption("Outil décisionnel basé sur **Google Earth Engine**, **Random Forest** et le **Deep Learning**. Auteur : Stephin MBOKOLO")

if not gee_ok:
    st.error(f"❌ Erreur d'initialisation Google Earth Engine : {gee_msg}")
    st.stop()

stats = compute_gee_stats(json.dumps(geo_json_payload), scale=scale_res)
if not stats["success"]:
    st.error(f"Erreur lors du traitement Earth Engine : {stats.get('error')}")
    st.stop()

# -----------------------------------------------------------------------------
# 7. MODULE 1 : OBSERVATOIRE SPATIAL (Version Conforme Jury)
# -----------------------------------------------------------------------------
if menu_option == "📊 Observatoire Spatiale":
    st.subheader(f"📊 Indicateurs Globaux de l'Occupation du Sol — {current_prov}")
    
    tot = stats["total"] if stats["total"] > 0 else 1.0
    p_pri, p_sec, p_def, p_oth = [(stats[k] / tot) * 100 for k in ["primary", "secondary", "deforestation", "other"]]
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Territoire", f"{stats['total']:,.0f} ha")
    c2.metric("Forêt Primaire", f"{stats['primary']:,.0f} ha", f"{p_pri:.1f}%")
    c3.metric("Forêt Secondaire", f"{stats['secondary']:,.0f} ha", f"{p_sec:.1f}%")
    c4.metric("Déforestation", f"{stats['deforestation']:,.0f} ha", f"{p_def:.1f}%")
    c5.metric("Autres", f"{stats['other']:,.0f} ha", f"{p_oth:.1f}%")
    
    st.markdown("---")
    st.markdown("### 🗺️ Carte d'Occupation du Sol (ESA WorldCover 10m - Référence Mondiale)")
    
    m = folium.Map(location=map_center, zoom_start=zoom_lvl, tiles="CartoDB positron")
    region_ee = ee.Geometry(geo_json_payload)

    # Chargement ESA WorldCover 10m
    esa = ee.ImageCollection("ESA/WorldCover/v200").first().clip(region_ee)
    layer_esa = add_ee_layer(esa, {'bands': ['Map']}, '🌍 Occupation du Sol (ESA)')
    layer_esa.add_to(m)

    if gdf_provinces is not None:
        folium.GeoJson(selected_gdf, name="Limites", style_function=lambda x: {'fillColor': 'transparent', 'color': '#000000', 'weight': 1.5}).add_to(m)
    
    if use_gps and gps_lat is not None and gps_lon is not None:
        folium.Marker([gps_lat, gps_lon], popup=f"<b>Point :</b> {gps_label}", icon=folium.Icon(color="red")).add_to(m)
    
    folium.LayerControl(collapsed=False).add_to(m)
    st_folium(m, width="100%", height=500)
    
    st.info("**Guide de lecture (ESA WorldCover 10m) :** 🟢 Forêt | 🟤 Savane | 🔵 Eau | 🔴 Déforestation/Bâti")
    
    st.markdown("---")
    st.markdown("### 🍩 Synthèse Proportionnelle")
    df_pie = pd.DataFrame({"Classe": ["Forêt Primaire", "Forêt Secondaire", "Déforestation", "Urbain/Savane"], "Superficie": [stats["primary"], stats["secondary"], stats["deforestation"], stats["other"]]})
    fig_pie = px.pie(df_pie, names="Classe", values="Superficie", hole=0.4, 
                     color_discrete_map={"Forêt Primaire":"#006400", "Forêt Secondaire":"#90EE90", "Déforestation":"#FF0000", "Urbain/Savane":"#D3D3D3"})
    st.plotly_chart(fig_pie, use_container_width=True)

# -----------------------------------------------------------------------------
# 8 à 10. RESTE DU CODE (SYSTÈME D'ALERTE, IA, EXPORTATIONS)
# -----------------------------------------------------------------------------
elif menu_option == "🚨 Système d'Alerte Précoce (RADD/Sentinel)":
    st.subheader(f"🚨 Détection Quasi-Temps Réel des Perturbations Forestières — {current_prov}")
    # [Code existant pour le module 2]
    
elif menu_option == "🔮 Modélisation Prospective & IA (2025-2035)":
    st.subheader(f"🔮 Projections & Modèles d'Intelligence Artificielle — {current_prov}")
    # [Code existant pour le module 3]

elif menu_option == "📥 Rapports & Exportations":
    st.subheader("📥 Exportation des Données et Synthèses Exécutives")
    # [Code existant pour le module 4]

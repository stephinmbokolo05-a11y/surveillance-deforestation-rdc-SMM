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
    page_title="Plateforme Nationale de Surveillance & Alerte Précoce (RDC)",
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
            json_creds = json.loads(st.secrets["GEE_JSON"])
            credentials = ee.ServiceAccountCredentials(
                json_creds["client_email"],
                key_data=st.secrets["GEE_JSON"]
            )
            ee.Initialize(credentials)
            return True, "Initialisation réussie via st.secrets."
        else:
            ee.Initialize()
            return True, "Initialisation réussie via authentification locale."
    except Exception as e:
        return False, str(e)

gee_ok, gee_msg = init_gee()

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
st.sidebar.title("⚙️ Paramètres de Navigation")

menu_option = st.sidebar.radio(
    "Navigation Fonctionnelle :",
    [
        "📊 Observatoire Spatiale",
        "🚨 Système d'Alerte Précoce",
        "🔮 Modélisation Prospective (2025-2035)",
        "📥 Rapports & Exportations"
    ]
)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Choix de la Zone d'Étude")

if gdf_provinces is not None and "NAME_1" in gdf_provinces.columns:
    provinces_list = sorted(gdf_provinces["NAME_1"].dropna().unique().tolist())
    select_options = ["🇨🇩 Toute la RDC (Vue Nationale)"] + provinces_list
    selected_option = st.sidebar.selectbox("Zone administrative :", select_options, index=select_options.index("Mai-Ndombe") if "Mai-Ndombe" in select_options else 0)
    
    if selected_option == "🇨🇩 Toute la RDC (Vue Nationale)":
        is_national = True
        current_prov = "Toute la RDC"
    else:
        is_national = False
        current_prov = selected_option
else:
    is_national = False
    current_prov = "Mai-Ndombe"
    st.sidebar.warning("Shapefile non détecté. Utilisation de la zone par défaut.")

# -----------------------------------------------------------------------------
# NOUVEAU : SECTION VÉRIFICATION DE TERRAIN (GPS)
# -----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("📌 Vérification de Terrain (GPS)")
use_gps = st.sidebar.checkbox("Activer un point de contrôle GPS", value=False)

gps_lat, gps_lon = None, None
if use_gps:
    # Coordonnées par défaut centrées sur le Mai-Ndombe/Cuvette centrale
    gps_lat = st.sidebar.number_input("Latitude (°N/S) :", value=-2.000000, format="%.6f")
    gps_lon = st.sidebar.number_input("Longitude (°E) :", value=18.300000, format="%.6f")
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
        lossyear = hansen.select('lossyear')
        
        primary_forest = treecover2000.gte(60).And(loss.eq(0))
        secondary_forest = treecover2000.gte(10).And(treecover2000.lt(60)).And(loss.eq(0))
        deforestation = loss.gt(0)
        
        pixel_area = ee.Image.pixelArea().divide(10000) # ha
        
        def get_area(mask_img):
            stat = mask_img.multiply(pixel_area).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=region,
                scale=scale,
                maxPixels=1e13,
                bestEffort=True
            )
            val = stat.getInfo()
            if val:
                key = list(val.keys())[0]
                return float(val[key]) if val[key] is not None else 0.0
            return 0.0

        area_primary = get_area(primary_forest)
        area_secondary = get_area(secondary_forest)
        area_deforest = get_area(deforestation)
        
        total_area = area_primary + area_secondary + area_deforest
        
        return {
            "success": True,
            "primary": area_primary,
            "secondary": area_secondary,
            "deforestation": area_deforest,
            "total": total_area
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Détermination de la géométrie sélectionnée
if gdf_provinces is not None:
    if is_national:
        selected_gdf = gdf_provinces
        scale_res = 1000
        zoom_lvl = 5
        map_center = [-2.5, 23.5]
    else:
        selected_gdf = gdf_provinces[gdf_provinces['NAME_1'] == current_prov]
        scale_res = 150
        centroid = selected_gdf.geometry.centroid.iloc[0]
        map_center = [centroid.y, centroid.x]
        zoom_lvl = 7
    
    geo_json_payload = selected_gdf.geometry.unary_union.__geo_interface__
else:
    map_center = [-2.0, 18.3]
    zoom_lvl = 7
    scale_res = 150
    geo_json_payload = {"type": "Point", "coordinates": [18.3, -2.0]}

# -----------------------------------------------------------------------------
# 6. EN-TÊTE PRINCIPAL
# -----------------------------------------------------------------------------
st.title("🌲 Plateforme Nationale de Surveillance, Prospective & Alerte Précoce (RDC)")
st.caption("Outil décisionnel basé sur **Google Earth Engine** et la modélisation spatio-temporelle.")

if not gee_ok:
    st.error(f"❌ Erreur d'initialisation Google Earth Engine : {gee_msg}")
    st.stop()

# Calcul des statistiques
with st.spinner(f"Calcul des indicateurs spatiaux pour {current_prov}..."):
    stats = compute_gee_stats(json.dumps(geo_json_payload), scale=scale_res)

if not stats["success"]:
    st.error(f"Erreur lors du traitement Earth Engine : {stats.get('error')}")
    st.stop()

# -----------------------------------------------------------------------------
# 7. MODULE 1 : OBSERVATOIRE SPATIAL
# -----------------------------------------------------------------------------
if menu_option == "📊 Observatoire Spatiale":
    st.subheader(f"📊 Indicateurs Globaux de l'Occupation du Sol — {current_prov}")
    
    tot = stats["total"] if stats["total"] > 0 else 1.0
    p_pri = (stats["primary"] / tot) * 100
    p_sec = (stats["secondary"] / tot) * 100
    p_def = (stats["deforestation"] / tot) * 100
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Territoire Analysé", f"{stats['total']:,.0f} ha")
    c2.metric("🟢 Forêt Primaire", f"{stats['primary']:,.0f} ha", f"{p_pri:.1f}%")
    c3.metric("🟡 Forêt Secondaire", f"{stats['secondary']:,.0f} ha", f"{p_sec:.1f}%")
    c4.metric("🔴 Déforestation Cumulée", f"{stats['deforestation']:,.0f} ha", f"{p_def:.1f}%")
    
    st.markdown("---")
    
    # Carte Folium
    m = folium.Map(location=map_center, zoom_start=zoom_lvl, tiles="OpenStreetMap")
    
    if gdf_provinces is not None:
        folium.GeoJson(
            selected_gdf,
            name="Limites Administratives",
            style_function=lambda x: {
                'fillColor': '#2e7d32',
                'color': '#1b5e20',
                'weight': 2,
                'fillOpacity': 0.1
            }
        ).add_to(m)
    
    # Ajout du point de contrôle GPS si activé
    if use_gps and gps_lat is not None and gps_lon is not None:
        folium.Marker(
            location=[gps_lat, gps_lon],
            popup=f"<b>Point Terrain :</b> {gps_label}<br>Lat: {gps_lat:.6f}, Lon: {gps_lon:.6f}",
            tooltip=f"📍 {gps_label}",
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(m)
        
        # Le centrage bascule directement sur le point GPS saisi
        m.location = [gps_lat, gps_lon]
        m.zoom_start = 12

    folium.LayerControl().add_to(m)
    
    col_map, col_chart = st.columns([2, 1])
    
    with col_map:
        st.markdown("**Carte Interactive & Contrôle Terrain**")
        st_folium(m, width="100%", height=500)
        if use_gps:
            st.info(f"📍 **Point de contrôle actif :** Latitude = `{gps_lat}`, Longitude = `{gps_lon}` ({gps_label})")
        
    with col_chart:
        st.markdown("**Répartition de l'Occupation**")
        df_pie = pd.DataFrame({
            "Classe": ["Forêt Primaire", "Forêt Secondaire", "Déforestation"],
            "Superficie": [stats["primary"], stats["secondary"], stats["deforestation"]]
        })
        fig_pie = px.pie(
            df_pie, 
            names="Classe", 
            values="Superficie",
            color="Classe",
            color_discrete_map={
                "Forêt Primaire": "#2e7d32",
                "Forêt Secondaire": "#fbc02d",
                "Déforestation": "#d32f2f"
            },
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# -----------------------------------------------------------------------------
# 8. MODULE 2 : SYSTÈME D'ALERTE PRÉCOCE
# -----------------------------------------------------------------------------
elif menu_option == "🚨 Système d'Alerte Précoce":
    st.subheader(f"🚨 Système d'Alerte Précoce et Pression Anthropique — {current_prov}")
    
    rate_def = (stats["deforestation"] / (stats["total"] if stats["total"] > 0 else 1)) * 100
    
    if rate_def > 15:
        level = "ROUGE (Vigilance Maximale)"
        color = "red"
        rec = "Intervention prioritaire requise : Renforcer les patrouilles de contrôle et geler les extensions agricoles non planifiées."
    elif rate_def > 5:
        level = "ORANGE (Pression Modérée)"
        color = "orange"
        rec = "Surveillance accrue recommandée : Promouvoir les alternatives agroforestières et sensibiliser les communautés locales."
    else:
        level = "VERT (Pression Faible)"
        color = "green"
        rec = "Zone sous contrôle : Maintenir les efforts de conservation et la surveillance communautaire continue."
        
    st.markdown(f"### Niveau de Vigilance : :{color}[**{level}**]")
    st.info(f"**Recommandation Opérationnelle :** {rec}")
    
    st.markdown("---")
    st.markdown("#### Facteurs de Pression Anthropique Estimés")
    col_a, col_b = st.columns(2)
    col_a.metric("Taux de Déforestation Observé", f"{rate_def:.2f} %")
    col_b.metric("Niveau de Risque pour la Biodiversité", "Élevé" if rate_def > 10 else "Modéré")

# -----------------------------------------------------------------------------
# 9. MODULE 3 : MODÉLISATION PROSPECTIVE (2025-2035)
# -----------------------------------------------------------------------------
elif menu_option == "🔮 Modélisation Prospective (2025-2035)":
    st.subheader(f"🔮 Projections de Perte du Couvert Forestier (2025–2035) — {current_prov}")
    
    years = list(range(2025, 2036))
    annual_loss = stats["deforestation"] / 20.0 if stats["deforestation"] > 0 else 1000.0
    
    baseline = [stats["primary"] - (annual_loss * (y - 2024)) for y in years]
    conservation = [stats["primary"] - ((annual_loss * 0.5) * (y - 2024)) for y in years]
    
    df_proj = pd.DataFrame({
        "Année": years,
        "Tendance Actuelle (Fil de l'eau)": baseline,
        "Scénario Conservation (REDD+)": conservation
    })
    
    fig_proj = go.Figure()
    fig_proj.add_trace(go.Scatter(x=df_proj["Année"], y=df_proj["Tendance Actuelle (Fil de l'eau)"], name="Tendances Actuelles", line=dict(color="#d32f2f", width=3)))
    fig_proj.add_trace(go.Scatter(x=df_proj["Année"], y=df_proj["Scénario Conservation (REDD+)"], name="Objectif REDD+ (-50%)", line=dict(color="#2e7d32", width=3, dash="dash")))
    
    fig_proj.update_layout(
        title="Évolution Projetée de la Forêt Primaire (Hectares)",
        xaxis_title="Année",
        yaxis_title="Superficie (ha)",
        legend_title="Scénarios"
    )
    
    st.plotly_chart(fig_proj, use_container_width=True)

# -----------------------------------------------------------------------------
# 10. MODULE 4 : RAPPORTS & EXPORTATIONS
# -----------------------------------------------------------------------------
elif menu_option == "📥 Rapports & Exportations":
    st.subheader("📥 Exportation des Données et Synthèses Exécutives")
    
    df_report = pd.DataFrame([{
        "Province": current_prov,
        "Foreating_Primary_ha": stats["primary"],
        "Forest_Secondary_ha": stats["secondary"],
        "Deforestation_ha": stats["deforestation"],
        "Total_ha": stats["total"]
    }])
    
    csv_data = df_report.to_csv(index=False).encode('utf-8')
    
    report_txt = f"""=== SYNTHÈSE EXÉCUTIVE DE SURVEILLANCE FORESTIÈRE ===
Zone : {current_prov}
Forêt Primaire : {stats['primary']:,.2f} ha
Forêt Secondaire : {stats['secondary']:,.2f} ha
Déforestation Cumulée : {stats['deforestation']:,.2f} ha
Superficie Totale : {stats['total']:,.2f} ha
======================================================
Generated via Streamlit National Forest Platform
"""
    
    col_d1, col_d2 = st.columns(2)
    col_d1.download_button("📊 Télécharger les statistiques (.CSV)", data=csv_data, file_name=f"stats_foret_{current_prov}.csv", mime="text/csv")
    col_d2.download_button("📄 Télécharger le Rapport Exécutif (.TXT)", data=report_txt, file_name=f"rapport_{current_prov}.txt", mime="text/plain")

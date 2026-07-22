import json
import os
import io
import streamlit as st
import geopandas as gpd
import ee
import folium
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Système National de Surveillance & Prospective RDC",
    page_icon="🌲",
    layout="wide"
)

st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #1b5e20;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🌲 Plateforme Nationale de Surveillance, Prospective & Alerte Précoce (RDC)")
st.markdown("Outil décisionnel basé sur **Google Earth Engine** et la modélisation spatio-temporelle.")

# --- INITIALISATION SÉCURISÉE CLOUD & LOCAL DE GEE ---
@st.cache_resource
def init_ee():
    try:
        if "GEE_JSON" in st.secrets:
            gee_sec = st.secrets["GEE_JSON"]
            if isinstance(gee_sec, str):
                credentials_dict = json.loads(gee_sec)
            else:
                credentials_dict = dict(gee_sec)
            credentials = ee.ServiceAccountCredentials(
                credentials_dict["client_email"], key_data=json.dumps(credentials_dict)
            )
            ee.Initialize(credentials)
        else:
            ee.Initialize()
    except Exception as e:
        st.error(f"Erreur d'initialisation Google Earth Engine : {e}")

init_ee()

# Gestion adaptable du chemin SHP
WORK_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else r"D:\PROJET_SUIVI_DEFORESTATION_RDC"
SHP_PATH = os.path.join(WORK_DIR, "SHPRDC", "gadm41_COD_1.shp")

@st.cache_data
def load_provinces(path):
    if os.path.exists(path):
        return gpd.read_file(path)
    return None

gdf_provinces = load_provinces(SHP_PATH)

# Calcul GEE avec region_id dynamique
@st.cache_data(ttl=3600)
def compute_gee_stats(geojson_dict, is_national, scale_resolution, region_id):
    if is_national:
        ee_geometry = ee.FeatureCollection(geojson_dict).geometry()
    else:
        ee_geometry = ee.Geometry(geojson_dict)
        
    hansen = ee.Image("UMD/hansen/global_forest_change_2022_v1_10").clip(ee_geometry)
    treecover = hansen.select("treecover2000")
    loss = hansen.select("loss")
    water_mask = hansen.select("datamask").eq(2)
    land_mask = water_mask.neq(1)
    
    foret_primaire = treecover.gte(75).And(loss.neq(1)).And(land_mask).updateMask(treecover.gte(75))
    foret_secondaire = treecover.gte(30).And(treecover.lt(75)).And(loss.neq(1)).And(land_mask).updateMask(treecover.gte(30).And(treecover.lt(75)))
    deforestation = loss.eq(1).And(land_mask).updateMask(loss.eq(1))
    plans_eau = water_mask.updateMask(water_mask)
    non_foret = treecover.lt(30).And(loss.neq(1)).And(land_mask).updateMask(treecover.lt(30))
    
    area_image = ee.Image.pixelArea().divide(10000) # Ha
    
    stats_prim = area_image.updateMask(foret_primaire).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geometry, scale=scale_resolution, maxPixels=1e11
    ).get('area')
    
    stats_sec = area_image.updateMask(foret_secondaire).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geometry, scale=scale_resolution, maxPixels=1e11
    ).get('area')
    
    stats_loss = area_image.updateMask(deforestation).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geometry, scale=scale_resolution, maxPixels=1e11
    ).get('area')
    
    stats_water = area_image.updateMask(plans_eau).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geometry, scale=scale_resolution, maxPixels=1e11
    ).get('area')

    stats_non_foret = area_image.updateMask(non_foret).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geometry, scale=scale_resolution, maxPixels=1e11
    ).get('area')
    
    return {
        'prim': stats_prim.getInfo() or 0,
        'sec': stats_sec.getInfo() or 0,
        'loss': stats_loss.getInfo() or 0,
        'water': stats_water.getInfo() or 0,
        'urban_savannah': stats_non_foret.getInfo() or 0
    }

st.sidebar.header("⚙️ Paramètres de Navigation")

# Onglets principaux
menu = st.sidebar.radio("Navigation Fonctionnelle :", [
    "📊 Observatoire Spatiale", 
    "🚨 Système d'Alerte Précoce", 
    "🔮 Modélisation Prospective (2025-2035)", 
    "📥 Rapports & Exportations"
])

if gdf_provinces is not None:
    provinces_list = ["🇨🇩 Toute la RDC (Vue Nationale)"] + sorted(gdf_provinces['NAME_1'].unique().tolist())
    selected_province = st.sidebar.selectbox("Zone d'analyse :", provinces_list)
else:
    selected_province = st.sidebar.text_input("Province", "Mai-Ndombe")

if st.sidebar.button("🚀 Lancer / Actualiser L'Analyse"):
    st.session_state["active_prov"] = selected_province

# Fixation de la zone active
if "active_prov" not in st.session_state:
    st.session_state["active_prov"] = selected_province

current_prov = st.session_state["active_prov"]
is_national = (current_prov == "🇨🇩 Toute la RDC (Vue Nationale)")

if is_national and gdf_provinces is not None:
    gdf_selected = gdf_provinces
    lat, lon = -2.5, 23.5
    zoom_level = 5
    region_name = "République Démocratique du Congo"
    geo_payload = gdf_selected.__geo_interface__
    scale_res = 1000
elif gdf_provinces is not None:
    gdf_selected = gdf_provinces[gdf_provinces['NAME_1'] == current_prov]
    centroid = gdf_selected.geometry.centroid.iloc[0]
    lat, lon = centroid.y, centroid.x
    zoom_level = 7
    region_name = current_prov
    geo_payload = gdf_selected.geometry.iloc[0].__geo_interface__
    scale_res = 150
else:
    lat, lon = -2.0, 18.3
    zoom_level = 7
    region_name = current_prov
    geo_payload = {"type": "Point", "coordinates": [lon, lat]}
    scale_res = 150

# Chargement centralisé des données
stats = compute_gee_stats(geo_payload, is_national, scale_res, region_name)
ha_prim = stats['prim']
ha_sec = stats['sec']
ha_loss = stats['loss']
ha_water = stats['water']
ha_other = stats['urban_savannah']
total_territoire = ha_prim + ha_sec + ha_loss + ha_water + ha_other

pct_prim = (ha_prim / total_territoire * 100) if total_territoire > 0 else 0
pct_sec = (ha_sec / total_territoire * 100) if total_territoire > 0 else 0
pct_loss = (ha_loss / total_territoire * 100) if total_territoire > 0 else 0

# --- ONGLET 1: OBSERVATOIRE SPATIAL ---
if menu == "📊 Observatoire Spatiale":
    st.subheader(f"📊 Indicateurs Globaux de l'Occupation du Sol — {region_name}")
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Territoire Total", f"{total_territoire:,.0f} ha")
    c2.metric("🟢 Forêt Primaire", f"{ha_prim:,.0f} ha", f"{pct_prim:.1f}%")
    c3.metric("🟡 Forêt Secondaire", f"{ha_sec:,.0f} ha", f"{pct_sec:.1f}%")
    c4.metric("🔴 Déforestation Cumulée", f"{ha_loss:,.0f} ha", f"{pct_loss:.1f}%", delta_color="inverse")
    c5.metric("🏘️ Savanes & Urbain", f"{ha_other:,.0f} ha")
    
    st.markdown("---")
    
    # Carte
    if is_national:
        ee_geom = ee.FeatureCollection(geo_payload).geometry()
    else:
        ee_geom = ee.Geometry(geo_payload)
        
    hansen = ee.Image("UMD/hansen/global_forest_change_2022_v1_10").clip(ee_geom)
    treecover = hansen.select("treecover2000")
    loss = hansen.select("loss")
    water_mask = hansen.select("datamask").eq(2)
    land_mask = water_mask.neq(1)
    
    foret_primaire = treecover.gte(75).And(loss.neq(1)).And(land_mask).updateMask(treecover.gte(75))
    foret_secondaire = treecover.gte(30).And(treecover.lt(75)).And(loss.neq(1)).And(land_mask).updateMask(treecover.gte(30).And(treecover.lt(75)))
    deforestation = loss.eq(1).And(land_mask).updateMask(loss.eq(1))
    plans_eau = water_mask.updateMask(water_mask)

    prim_map = ee.Image(foret_primaire).getMapId({'palette': ['#004d40']}) 
    sec_map = ee.Image(foret_secondaire).getMapId({'palette': ['#81c784']}) 
    loss_map = ee.Image(deforestation).getMapId({'palette': ['#d32f2f']})   
    water_map = ee.Image(plans_eau).getMapId({'palette': ['#0288d1']}) 

    m = folium.Map(location=[lat, lon], zoom_start=zoom_level, tiles="OpenStreetMap")
    
    folium.TileLayer(tiles=water_map['tile_fetcher'].url_format, attr='GEE', name="Lacs, Fleuves & Rivières", overlay=True).add_to(m)
    folium.TileLayer(tiles=prim_map['tile_fetcher'].url_format, attr='GEE', name='Forêt Dense Primaire', overlay=True).add_to(m)
    folium.TileLayer(tiles=sec_map['tile_fetcher'].url_format, attr='GEE', name='Forêt Secondaire / Dégradée', overlay=True).add_to(m)
    folium.TileLayer(tiles=loss_map['tile_fetcher'].url_format, attr='GEE', name='Déforestation / Pertes', overlay=True).add_to(m)
    
    if gdf_provinces is not None:
        folium.GeoJson(gdf_selected.__geo_interface__, name=f"Limites {region_name}", style_function=lambda x: {'fillColor': 'transparent', 'color': '#000', 'weight': 2, 'dashArray': '4, 4'}).add_to(m)
    
    folium.LayerControl().add_to(m)
    components.html(m._repr_html_(), height=550)

# --- ONGLET 2: ALERTE PRÉCOCE ---
elif menu == "🚨 Système d'Alerte Précoce":
    st.subheader(f"🚨 Module National d'Alerte Précoce — {region_name}")
    
    taux_pression = (ha_loss / (ha_prim + ha_sec + 1e-5)) * 100
    
    if taux_pression > 10:
        st.error(f"⚠️ **STATUT : VIGILANCE ROUGE** — Taux de pression anthropique très élevé ({taux_pression:.2f}% de la forêt totale). Intervention prioritaire recommandée.")
    elif taux_pression > 4:
        st.warning(f"🟧 **STATUT : VIGILANCE ORANGE** — Pression modérée détectée ({taux_pression:.2f}%). Risques de mitage forestier.")
    else:
        st.success(f"🟢 **STATUT : VIGILANCE VERTE** — Écosystème relativement préservé ({taux_pression:.2f}%).")

    col_a, col_b = st.columns(2)
    with col_a:
        st.info("📌 **Facteurs de Pression Anthropique Détectés**")
        st.markdown("- Agriculture itinérante sur brûlis dans les zones périurbaines.\n- Exploitation artisanale du bois d'énergie (charbon/makala).\n- Extension des voies d'accès routières non stabilisées.")
    with col_b:
        st.info("🛡️ **Recommandations Stratégiques REDD+**")
        st.markdown("- Renforcement des patrouilles de surveillance de proximité.\n- Encouragement des concessions forestières des communautés locales (CFCL).\n- Promotion des foyers améliorés pour réduire la coupe de bois.")

# --- ONGLET 3: MODÉLISATION PROSPECTIVE (2025-2035) ---
elif menu == "🔮 Modélisation Prospective (2025-2035)":
    st.subheader(f"🔮 Simulation Prospective de la Déforestation (2025–2035) — {region_name}")
    st.caption("Modèle d'extrapolation linéaire basé sur le taux moyen annuel historique d'émondage du couvert arboré.")

    annees = np.arange(2025, 2036)
    perte_annuelle_moyenne = ha_loss / 20.0 
    
    projections_loss = [ha_loss + (perte_annuelle_moyenne * (yr - 2024)) for yr in annees]
    projections_prim = [max(0, ha_prim - (perte_annuelle_moyenne * 0.7 * (yr - 2024))) for yr in annees]
    
    fig_proj = go.Figure()
    fig_proj.add_trace(go.Scatter(x=annees, y=projections_loss, mode='lines+markers', name='Déforestation Cumulée (Projetée)', line=dict(color='#d32f2f', width=3)))
    fig_proj.add_trace(go.Scatter(x=annees, y=projections_prim, mode='lines+markers', name='Forêt Primaire Rescapée', line=dict(color='#004d40', width=3)))
    
    fig_proj.update_layout(title=f"Trajectoire des Écosystèmes (2025–2035) à politique constante — {region_name}", xaxis_title="Année", yaxis_title="Superficie (Hectares)", hovermode="x unified")
    st.plotly_chart(fig_proj, use_container_width=True)
    
    st.warning(f"💡 **Projection en 2035** : Sans mesure corrective, la zone risque de perdre **{perte_annuelle_moyenne * 11:,.0f} hectares** supplémentaires de forêt d'ici 2035.")

# --- ONGLET 4: RAPPORTS & EXPORTATIONS ---
elif menu == "📥 Rapports & Exportations":
    st.subheader(f"📥 Centre de Téléchargement & Exportation — {region_name}")
    
    df_export = pd.DataFrame({
        'Région / Province': [region_name],
        'Superficie Totale (ha)': [total_territoire],
        'Forêt Primaire (ha)': [ha_prim],
        'Forêt Secondaire (ha)': [ha_sec],
        'Déforestation Cumulée (ha)': [ha_loss],
        'Lacs & Fleuves (ha)': [ha_water],
        'Savanes & Urbain (ha)': [ha_other],
        'Taux Forêt Primaire (%)': [pct_prim],
        'Taux Déforestation (%)': [pct_loss]
    })
    
    st.markdown("### 1. Exportation des données brutes (Excel / CSV)")
    csv_buffer = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📄 Télécharger les Statistiques Officiels (Format CSV)",
        data=csv_buffer,
        file_name=f"Bilan_Forestier_{region_name.replace(' ', '_')}.csv",
        mime="text/csv"
    )
    
    st.markdown("---")
    st.markdown("### 2. Synthèse Exécutive Imprimable")
    
    rapport_txt = f"""=== RAPPORT NATIONAL DE SURVEILLANCE FORESTIÈRE ===
Région Analysée : {region_name}
Superficie Totale Evaluée : {total_territoire:,.0f} ha

--- BILAN CARTOGRAPHIQUE ET SPATIAL ---
1. Forêt Dense Primaire : {ha_prim:,.0f} ha ({pct_prim:.2f}%)
2. Forêt Secondaire / Mosaïque : {ha_sec:,.0f} ha ({pct_sec:.2f}%)
3. Pertes / Déforestation : {ha_loss:,.0f} ha ({pct_loss:.2f}%)
4. Hydrographie (Lacs & Fleuves) : {ha_water:,.0f} ha
5. Savanes, Terres Agricoles & Urbain : {ha_other:,.0f} ha

Source des données : Google Earth Engine / Hansen Global Forest Change
Analyse générée par la Plateforme Nationale de Surveillance de la RDC.
"""
    st.text_area("Aperçu du Rapport Synthétique :", rapport_txt, height=200)
    st.download_button(
        label="🖨️ Télécharger le Rapport Exécutif (.TXT)",
        data=rapport_txt,
        file_name=f"Rapport_Execution_{region_name.replace(' ', '_')}.txt",
        mime="text/plain"
    )

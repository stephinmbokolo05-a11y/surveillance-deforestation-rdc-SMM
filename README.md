# surveillance-deforestation-rdc-SMM
Plateforme nationale de surveillance forestière, modélisation prospective et système d'alerte précoce pour la RDC
# 🌲 Plateforme Nationale de Surveillance, Prospective & Alerte Précoce de la Déforestation en RDC

Une application décisionnelle interactive développée avec **Streamlit**, **Google Earth Engine (GEE)** et **GeoPandas** pour le suivi dynamique du couvert forestier, la modélisation prospective et l'alerte précoce sur la pression anthropique en République Démocratique du Congo.

---

## 📌 Contextes et Objectifs
La République Démocratique du Congo (RDC) abrite la plus grande superficie de forêts denses humides du bassin du Congo. Face aux enjeux de la transition écologique, de la conservation de la biodiversité et des mécanismes REDD+, cette plateforme vise à :
1. **Évaluer et cartographier** dynamiquement l'occupation du sol (forêts primaires, forêts secondaires, déforestation et hydrographie).
2. **Modéliser les trajectoires prospectives (2025–2035)** de la perte du couvert arboré à politique constante.
3. **Fournir un système d'alerte précoce** basé sur des indicateurs de pression anthropique à l'échelle provinciale et nationale.
4. **Faciliter la prise de décision** via l'exportation de données statistiques et de synthèses exécutives imprimables.

---

## 🛠️ Architecture Technique & Technologies

- **Frontend & Dashboarding** : [Streamlit](https://streamlit.io/)
- **Traitement Geospatial & Satellite Cloud** : [Google Earth Engine (GEE API)](https://earthengine.google.com/)
- **Analyse de Données Vectorielles** : [GeoPandas](https://geopandas.org/), [Shapely](https://shapely.readthedocs.io/)
- **Cartographie Interactive** : [Folium](https://python-visualization.github.io/folium/)
- **Visualisation & Graphiques Prospectifs** : [Plotly Express & Graph Objects](https://plotly.com/python/)
- **Données Satellites** : *Hansen Global Forest Change v1.11 (2000–2023)* / UMD

---

## 🚀 Fonctionnalités Clés

### 📊 1. Observatoire Spatial
- Choix de la zone d'étude : **Vue Nationale (🇨🇩 Toute la RDC)** ou **Niveau Provincial** (ex. Mai-Ndombe, Équateur, Tshuapa, etc.).
- Calcul dynamique des superficies (en hectares et pourcentages) des différentes classes d'occupation des terres.
- Cartographie interactive multi-couches (Forêt dense primaire, Forêt secondaire, Déforestation cumulée, Réseau hydrographique).

### 🚨 2. Système d'Alerte Précoce
- Calcul automatique d'un indice de pression anthropique.
- Classification de la vigilance par codes couleur (🟢 Vert, 🟧 Orange, ⚠️ Rouge).
- Recommandations opérationnelles orientées REDD+ et gouvernance locale.

### 🔮 3. Modélisation Prospective (2025–2035)
- Trajectoire d'extrapolation linéaire de la déforestation à l'horizon 2035.
- Évaluation des pertes forestières évitables selon les scénarios d'intervention.

### 📥 4. Rapports & Exportations
- Téléchargement des statistiques sous format structuré CSV.
- Génération et exportation de comptes rendus exécutifs synthétiques (.txt).

---

## 📂 Structure du Répertoire

```text
├── app.py                  # Code principal du tableau de bord Streamlit
├── requirements.txt        # Dépendances et bibliothèques Python
├── gadm41_COD_1.shp        # Fichier vecteur des limites administratives (Provinces RDC)
├── gadm41_COD_1.dbf        # Données attributaires associées
├── gadm41_COD_1.shx        # Index spatial du Shapefile
├── gadm41_COD_1.prj        # Système de projection géographique (WGS84)
└── README.md               # Documentation globale du projet

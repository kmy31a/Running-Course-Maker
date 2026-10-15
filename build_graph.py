"""송도 보행 그래프를 OSM에서 추출해 풍경 태그를 부여하고 저장한다."""
import osmnx as ox, networkx as nx

CENTER = (37.3925, 126.6370)   # 센트럴파크 부근
DIST = 4500                    # m

G = ox.graph_from_point(CENTER, dist=DIST, network_type="walk", simplify=True)
G = ox.project_graph(G, to_crs="EPSG:4326")

def feats(tags, **kw):
    try:
        return ox.features_from_point(CENTER, tags=tags, dist=DIST)
    except Exception:
        return None

park = feats({"leisure": ["park", "garden"]})
water = feats({"natural": ["water", "coastline", "bay"], "waterway": True})

def near(gdf, x, y, r=0.0004):   # ~40m
    if gdf is None or gdf.empty: return False
    from shapely.geometry import Point
    return bool(gdf.geometry.distance(Point(x, y)).min() < r)

# 속도를 위해 공간 인덱스 사용
from shapely.geometry import Point
def build_idx(g):
    return None if g is None or g.empty else (g.geometry.union_all() if hasattr(g.geometry,'union_all') else g.geometry.unary_union)
pu, wu = build_idx(park), build_idx(water)

for u, v, k, d in G.edges(keys=True, data=True):
    mx = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2
    my = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
    p = Point(mx, my)
    tags = []
    if pu is not None and pu.distance(p) < 0.0004: tags.append("공원")
    if wu is not None and wu.distance(p) < 0.0004: tags.append("수변")
    if not tags: tags.append("도심")
    d["scenery"] = tags
    d.pop("geometry", None)

ox.save_graphml(G, "songdo/data/songdo.graphml")
print(len(G.nodes), "nodes", len(G.edges), "edges")
from collections import Counter
print(Counter(t for _,_,d in G.edges(data=True) for t in d["scenery"]))

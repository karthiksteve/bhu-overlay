import sys, os
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
try:
    import subdivide
except ImportError:
    from backend import geometry as subdivide

def test_subdivide_imports_without_numpy():
    assert hasattr(subdivide, "generate_strategies")

def test_subdivide_eight_shares():
    from shapely.geometry import Polygon
    poly = Polygon([(0, 0), (100, 0), (100, 40), (0, 40)])
    strategies = subdivide.generate_strategies(poly, [1] * 8)
    assert len(strategies) >= 1
    assert len(strategies[0]["polys"]) == 8


"""
STL Analyzer - Pure Python implementation for printability analysis

Supports ASCII and Binary STL formats without external dependencies.
Computes geometry metrics and proof score (0-100) for 3D printability.
"""

import math
import struct
from typing import Optional


def analyze_stl(stl_path: str) -> dict:
    """
    Pure Python STL analyzer supporting ASCII and Binary formats.
    
    Args:
        stl_path: Absolute filesystem path to STL file
    
    Returns:
        {
            "triangles": int,
            "bbox_mm": [x, y, z],
            "volume_mm3": float | null,
            "weight_g": float | null,
            "overhang_percent": float,
            "non_manifold_edges": int,
            "degenerate_faces": int,
            "warnings": ["non_manifold", "degenerate_faces", ...],
            "proof_score": int (0-100)
        }
    """
    try:
        with open(stl_path, 'rb') as f:
            # Detect ASCII vs Binary
            header = f.read(5)
            f.seek(0)
            
            is_ascii = header.lower().startswith(b'solid')
            
            if is_ascii:
                triangles = _parse_ascii_stl(f)
            else:
                triangles = _parse_binary_stl(f)
        
        if not triangles:
            return {
                "triangles": 0,
                "bbox_mm": [0, 0, 0],
                "volume_mm3": None,
                "weight_g": None,
                "overhang_percent": 0,
                "non_manifold_edges": 0,
                "degenerate_faces": 0,
                "warnings": ["empty_mesh"],
                "proof_score": 0
            }
        
        # Compute bounding box
        bbox = _compute_bbox(triangles)
        
        # Check manifold (edge counts)
        is_manifold, non_manifold_count = _check_manifold(triangles)
        
        # Check degenerate faces
        degenerate_count = _count_degenerate_faces(triangles)
        
        # Compute overhang percentage
        overhang_percent = _compute_overhang(triangles)
        
        # Compute volume (may be unreliable for non-manifold)
        volume_mm3 = _compute_volume(triangles)
        volume_reliable = is_manifold and degenerate_count == 0
        
        # Estimate weight (PLA density 1.24 g/cm³)
        weight_g = None
        if volume_mm3 and volume_reliable:
            weight_g = (volume_mm3 / 1000.0) * 1.24
        
        # Warnings
        warnings = []
        if not is_manifold:
            warnings.append("non_manifold")
        if degenerate_count > 0:
            warnings.append("degenerate_faces")
        if not volume_reliable and volume_mm3:
            warnings.append("volume_unreliable")
        
        # Proof score heuristic
        proof_score = _compute_proof_score(is_manifold, degenerate_count, overhang_percent)
        
        return {
            "triangles": len(triangles),
            "bbox_mm": [round(bbox[0], 2), round(bbox[1], 2), round(bbox[2], 2)],
            "volume_mm3": round(volume_mm3, 2) if volume_mm3 else None,
            "weight_g": round(weight_g, 1) if weight_g else None,
            "overhang_percent": round(overhang_percent, 1),
            "non_manifold_edges": non_manifold_count,
            "degenerate_faces": degenerate_count,
            "warnings": warnings,
            "proof_score": proof_score
        }
        
    except Exception as e:
        return {
            "triangles": 0,
            "bbox_mm": [0, 0, 0],
            "volume_mm3": None,
            "weight_g": None,
            "overhang_percent": 0,
            "non_manifold_edges": 0,
            "degenerate_faces": 0,
            "warnings": ["parse_error"],
            "proof_score": 0,
            "error": str(e)
        }


def _parse_binary_stl(f) -> list:
    """Parse binary STL format"""
    f.read(80)  # Skip 80-byte header
    triangle_count_data = f.read(4)
    if len(triangle_count_data) < 4:
        return []
    
    triangle_count = struct.unpack('<I', triangle_count_data)[0]
    
    triangles = []
    for _ in range(triangle_count):
        # Normal vector (3 floats)
        normal_data = f.read(12)
        if len(normal_data) < 12:
            break
        nx, ny, nz = struct.unpack('<fff', normal_data)
        
        # 3 vertices (9 floats)
        v1_data = f.read(12)
        v2_data = f.read(12)
        v3_data = f.read(12)
        
        if len(v1_data) < 12 or len(v2_data) < 12 or len(v3_data) < 12:
            break
        
        v1 = struct.unpack('<fff', v1_data)
        v2 = struct.unpack('<fff', v2_data)
        v3 = struct.unpack('<fff', v3_data)
        
        f.read(2)  # Attribute byte count (skip)
        
        triangles.append({
            'normal': (nx, ny, nz),
            'vertices': [v1, v2, v3]
        })
    
    return triangles


def _parse_ascii_stl(f) -> list:
    """Parse ASCII STL format"""
    triangles = []
    vertices: list[tuple[float, float, float]] = []
    normal = None
    
    for line in f:
        try:
            line = line.decode('utf-8', errors='ignore').strip().lower()
        except:
            continue
        
        if line.startswith('facet normal'):
            parts = line.split()
            if len(parts) >= 5:
                try:
                    normal = (float(parts[2]), float(parts[3]), float(parts[4]))
                    vertices = []
                except ValueError:
                    continue
        
        elif line.startswith('vertex'):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    continue
        
        elif line.startswith('endfacet'):
            if len(vertices) == 3 and normal:
                triangles.append({
                    'normal': normal,
                    'vertices': vertices
                })
    
    return triangles


def _compute_bbox(triangles) -> list:
    """Compute bounding box [width, depth, height] in mm"""
    if not triangles:
        return [0, 0, 0]
    
    all_vertices = []
    for tri in triangles:
        all_vertices.extend(tri['vertices'])
    
    if not all_vertices:
        return [0, 0, 0]
    
    xs = [v[0] for v in all_vertices]
    ys = [v[1] for v in all_vertices]
    zs = [v[2] for v in all_vertices]
    
    return [
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs)
    ]


def _check_manifold(triangles) -> tuple:
    """
    Check if mesh is manifold (each edge shared by exactly 2 faces).
    Returns (is_manifold: bool, non_manifold_edge_count: int)
    """
    edge_counts: dict[tuple[float, float, float], int] = {}
    
    for tri in triangles:
        v = tri['vertices']
        # Create sorted edge tuples (use rounded coords to handle floating point errors)
        v0_key = tuple(round(x, 6) for x in v[0])
        v1_key = tuple(round(x, 6) for x in v[1])
        v2_key = tuple(round(x, 6) for x in v[2])
        
        edges = [
            tuple(sorted([v0_key, v1_key])),
            tuple(sorted([v1_key, v2_key])),
            tuple(sorted([v2_key, v0_key])),
        ]
        
        for edge in edges:
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    
    # Manifold: all edges appear exactly 2 times
    non_manifold = sum(1 for cnt in edge_counts.values() if cnt != 2)
    
    return (non_manifold == 0, non_manifold)


def _count_degenerate_faces(triangles) -> int:
    """Count triangles with near-zero area"""
    count = 0
    
    for tri in triangles:
        v0, v1, v2 = tri['vertices']
        
        # Edge vectors
        e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
        e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
        
        # Cross product magnitude = 2 * area
        cross = (
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        )
        
        mag = (cross[0]**2 + cross[1]**2 + cross[2]**2) ** 0.5
        
        if mag < 1e-6:
            count += 1
    
    return count


def _compute_overhang(triangles) -> float:
    """
    Compute percentage of faces with overhang (normal pointing down > 45°).
    Returns percentage (0-100).
    """
    if not triangles:
        return 0.0
    
    overhang_count = 0
    cos_45 = math.cos(math.radians(45))  # ~0.707
    
    for tri in triangles:
        nx, ny, nz = tri['normal']
        
        # Overhang: normal points down (nz < -cos_45)
        if nz < -cos_45:
            overhang_count += 1
    
    return (overhang_count / len(triangles)) * 100.0


def _compute_volume(triangles) -> Optional[float]:
    """
    Compute volume using signed tetrahedra method.
    Only reliable for manifold, watertight meshes.
    """
    if not triangles:
        return None
    
    volume = 0.0
    
    for tri in triangles:
        v0, v1, v2 = tri['vertices']
        
        # Signed tetrahedra: V = (v0 · (v1 × v2)) / 6
        cross = (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0]
        )
        
        dot = v0[0] * cross[0] + v0[1] * cross[1] + v0[2] * cross[2]
        volume += dot / 6.0
    
    return abs(volume) if volume != 0 else None


def _compute_proof_score(is_manifold: bool, degenerate_count: int, overhang_percent: float) -> int:
    """
    Compute proof score 0-100 using heuristic penalties.
    
    Penalties:
    - Non-manifold: -20
    - Degenerate faces: -10
    - Overhang: -1 per 10%
    """
    score = 100
    
    if not is_manifold:
        score -= 20
    
    if degenerate_count > 0:
        score -= 10
    
    # -1 per 10% overhang
    score -= int(overhang_percent / 10)
    
    return max(0, min(100, score))

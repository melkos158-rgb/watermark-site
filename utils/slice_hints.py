"""
Slice Hints Engine - Auto-generated print settings based on printability analysis.
Pure function with no Flask/DB dependencies.
"""

from datetime import datetime


def generate_slice_hints(printability: dict, proof_score: int) -> dict:
    """
    Generate heuristic print settings based on printability analysis.
    Must NEVER raise exceptions.
    
    Args:
        printability: Dict from STL analyzer (bbox, volume, overhang_percent, etc.)
        proof_score: Integer 0-100 printability score
    
    Returns:
        Dict with layer_height, infill_percent, supports, material, warnings, etc.
    """
    # Default settings
    layer_height = 0.2
    infill = 15
    supports = "none"
    material = "PLA"
    warnings = []
    
    # Safe reads from printability (handle None/missing gracefully)
    if printability is None:
        printability = {}
    
    printability.get("bbox") or {}
    volume = printability.get("volume") or 0
    overhang = printability.get("overhang_percent") or 0
    manifold = printability.get("manifold", True)
    deg_faces = printability.get("degenerate_faces", 0)
    
    # Ensure proof_score is valid integer
    if proof_score is None:
        proof_score = 50
    proof_score = max(0, min(int(proof_score), 100))
    
    # 1. Layer height (clamped)
    if proof_score >= 85:
        layer_height = 0.2
    elif proof_score >= 70:
        layer_height = 0.24
    else:
        layer_height = 0.28
    
    layer_height = max(0.16, min(layer_height, 0.28))
    
    # 2. Infill
    if volume < 20:
        infill = 20
    elif volume < 100:
        infill = 15
    else:
        infill = 10
    
    if proof_score < 60:
        infill += 5
    
    # 3. Supports
    if overhang < 10:
        supports = "none"
    elif overhang < 25:
        supports = "buildplate"
    else:
        supports = "everywhere"
    
    if not manifold:
        supports = "everywhere"
        warnings.append("Non-manifold geometry detected")
    
    # 4. Material (simple heuristic)
    estimated_time = (volume * 0.05) / max(layer_height, 0.01)
    if estimated_time > 8:
        material = "PLA+"
    
    # 5. Warnings
    if overhang > 30:
        warnings.append("High overhangs detected (>45°)")
    if deg_faces > 0:
        warnings.append("Degenerate faces detected")
    if proof_score < 50:
        warnings.append("Model may be hard to print")
    
    return {
        "layer_height": round(layer_height, 2),
        "infill_percent": int(infill),
        "supports": supports,
        "material": material,
        "estimated_time_hours": round(estimated_time, 1),
        "warnings": warnings,
        "generated_at": datetime.utcnow().isoformat()
    }

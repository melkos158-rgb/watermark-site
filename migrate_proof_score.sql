-- ============================================
-- Proof Score Migration
-- Add printability analysis fields to market_item
-- Date: 2025-12-15
-- ============================================

-- ============================================
-- PostgreSQL (Railway Production)
-- ============================================
-- Run this on Railway PostgreSQL database

ALTER TABLE market_item ADD COLUMN IF NOT EXISTS printability_json TEXT;
ALTER TABLE market_item ADD COLUMN IF NOT EXISTS proof_score INTEGER;
ALTER TABLE market_item ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP;

-- ============================================
-- SQLite (Local Development)
-- ============================================
-- Run this on local SQLite database

-- SQLite doesn't support IF NOT EXISTS in ALTER TABLE
-- Check if columns exist first, then run:

ALTER TABLE market_item ADD COLUMN printability_json TEXT;
ALTER TABLE market_item ADD COLUMN proof_score INTEGER;
ALTER TABLE market_item ADD COLUMN analyzed_at TEXT;

-- ============================================
-- Notes:
-- ============================================
-- printability_json: JSON string with detailed metrics
--   {
--     "triangles": 1234,
--     "bbox_mm": [x, y, z],
--     "volume_mm3": 5678.9,
--     "weight_g": 7.05,
--     "overhang_percent": 15.2,
--     "warnings": ["non_manifold", "degenerate_faces"]
--   }
--
-- proof_score: 0-100 heuristic score
--   100 = perfect printability
--   0 = major issues
--
-- analyzed_at: timestamp of last analysis
--   Used for cache invalidation
-- ============================================

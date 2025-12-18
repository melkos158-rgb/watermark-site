-- Migration: Add video preview + upload manager fields to market_items (items table)
-- Date: 2025-12-18
-- Description: Enables Cults-style video hover preview + background upload with progress

-- 🎬 VIDEO PREVIEW FIELDS
ALTER TABLE items ADD COLUMN IF NOT EXISTS video_url VARCHAR(500);
ALTER TABLE items ADD COLUMN IF NOT EXISTS video_duration INTEGER;

-- 📦 UPLOAD STATE FIELDS (for background upload with progress bar)
ALTER TABLE items ADD COLUMN IF NOT EXISTS upload_status VARCHAR(20) DEFAULT 'published';
ALTER TABLE items ADD COLUMN IF NOT EXISTS upload_progress INTEGER DEFAULT 100;

-- 📁 DIRECT UPLOAD TRACKING
ALTER TABLE items ADD COLUMN IF NOT EXISTS stl_upload_id VARCHAR(100);
ALTER TABLE items ADD COLUMN IF NOT EXISTS zip_upload_id VARCHAR(100);

-- 📌 PUBLISH STATE (for draft workflow)
ALTER TABLE items ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT TRUE;

-- Create index for filtering drafts
CREATE INDEX IF NOT EXISTS idx_items_upload_status ON items(upload_status);
CREATE INDEX IF NOT EXISTS idx_items_is_published ON items(is_published);

-- Comment explaining status values
COMMENT ON COLUMN items.upload_status IS 'draft | uploading | processing | published | failed';
COMMENT ON COLUMN items.upload_progress IS 'Upload progress percentage (0-100)';
COMMENT ON COLUMN items.video_url IS 'Short preview video (5-15sec, muted loop) from Cloudinary';
COMMENT ON COLUMN items.video_duration IS 'Video duration in seconds';

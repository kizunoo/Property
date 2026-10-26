-- Migration: 20261023110000_robot_neighborhood_nullable.sql
-- Purpose:
--   Allow real robots to have a NULL neighborhood (no physical location / geo signal)
BEGIN;

ALTER TABLE public.properties
  ALTER COLUMN neighborhood DROP NOT NULL;

COMMIT;

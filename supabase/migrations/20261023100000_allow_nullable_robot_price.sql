-- Migration: 20261023100000_allow_nullable_robot_price.sql
-- Purpose:
--   1. Allow robots (properties) with no price yet by dropping NOT NULL on property_value
--   2. Allow evaluations with no expected value yet by dropping NOT NULL on expected_value
BEGIN;

ALTER TABLE public.properties
  ALTER COLUMN property_value DROP NOT NULL,
  ALTER COLUMN property_value DROP DEFAULT,
  ALTER COLUMN property_value SET DEFAULT NULL;

ALTER TABLE public.pipeline_evaluations
  ALTER COLUMN expected_value DROP NOT NULL,
  ALTER COLUMN expected_value DROP DEFAULT,
  ALTER COLUMN expected_value SET DEFAULT NULL;

COMMIT;

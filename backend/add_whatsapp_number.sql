-- =============================================================================
-- Migration: Add WhatsApp Phone Number to Clients Table
-- =============================================================================
-- Run this in your Supabase SQL Editor:

alter table clients add column if not exists whatsapp_number text;

-- Backfill test numbers registered in your Meta WhatsApp Developer Dashboard:
-- Format: country code without '+' or spaces, e.g. 60109722730
update clients 
set whatsapp_number = '60109722730' 
where name in ('Precision Micro-Mechanics', 'Titan Manufacturing Corp');

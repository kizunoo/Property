-- -----------------------------------------------------------------------------
-- PIPELINE.EV Seed Data Extension: 15 Properties & 40 Clients
-- Run this in your Supabase SQL Editor to populate additional real estate data.
-- After running this SQL, trigger POST /api/run_evaluations to calculate scores!
-- -----------------------------------------------------------------------------

-- 1. INSERT 15 LUXURY PROPERTIES
INSERT INTO properties (address, neighborhood, property_value) VALUES
  ('Residensi 22, Unit 18-3', 'Mont Kiara', 1950000),
  ('The Serai, Unit 10-2', 'Bangsar', 4800000),
  ('Pavilion Residences, Tower B-22', 'KLCC', 3800000),
  ('One Menerung, Villa 5', 'Bangsar', 6200000),
  ('10 Mont Kiara, High Floor Unit', 'Mont Kiara', 2650000),
  ('Desa Green, Block A-12', 'Taman Desa', 750000),
  ('Sunway Vivaldi, Block C', 'Mont Kiara', 3100000),
  ('Aira Residences, Penthouse 2', 'Damansara Heights', 8500000),
  ('The Westside III, Unit 25-1', 'Desa ParkCity', 1450000),
  ('Suria KLCC Serviced Suites', 'KLCC', 2200000),
  ('Banyan Tree Signatures, Unit 33-05', 'KLCC', 4100000),
  ('Damansara City Residences, Tower B', 'Damansara Heights', 2900000),
  ('Villa Serene Kiara, Bungalow 12', 'Mont Kiara', 5500000),
  ('The RuMa Residences, Suite 19', 'KLCC', 1800000),
  ('Seresta Residences, Block A-08', 'Bandar Sri Damansara', 920000);

-- 2. INSERT 40 CLIENTS
INSERT INTO clients (name, stated_budget, preferred_neighborhood, past_viewings) VALUES
  ('Farhan Abdullah', 5000000, 'Damansara Heights', 4),
  ('Chung Wei Ming', 2200000, 'Mont Kiara', 2),
  ('Siti Nurhaliza Ismail', 4500000, 'KLCC', 3),
  ('Vikram Naidu', 1800000, 'Desa ParkCity', 1),
  ('Melissa Tan', 6500000, 'Bangsar', 5),
  ('Kavita Sharma', 1200000, 'Taman Desa', 0),
  ('Benjamin Lee', 3200000, 'Mont Kiara', 2),
  ('Nurul Izzah Anwar', 2800000, 'Bangsar', 3),
  ('Jason Wong', 900000, 'Bandar Sri Damansara', 0),
  ('Tariq Mansor', 8000000, 'Damansara Heights', 4),
  ('Grace Cheah', 3900000, 'KLCC', 2),
  ('Dinesh Kumar', 1500000, 'Desa ParkCity', 1),
  ('Zulkipli Harun', 2100000, 'Mont Kiara', 3),
  ('Stephanie Yap', 4200000, 'KLCC', 1),
  ('Marcus Chin', 5800000, 'Bangsar', 4),
  ('Anita Raj', 1100000, 'Taman Desa', 0),
  ('Syed Mokhtar', 10000000, 'Damansara Heights', 5),
  ('Chloe Ng', 2700000, 'Mont Kiara', 2),
  ('Imran Hussein', 3500000, 'KLCC', 3),
  ('Devi Subramaniam', 1600000, 'Desa ParkCity', 1),
  ('Adrian Soo', 4900000, 'Bangsar', 2),
  ('Zahra Al-Hadi', 2300000, 'Mont Kiara', 1),
  ('Kevin Low', 850000, 'Bandar Sri Damansara', 0),
  ('Nadia Kamal', 3100000, 'Damansara Heights', 2),
  ('Alvin Teoh', 4000000, 'KLCC', 3),
  ('Priya Pillai', 1350000, 'Desa ParkCity', 0),
  ('Roslan Ahmad', 6000000, 'Bangsar', 4),
  ('Michelle Liew', 2500000, 'Mont Kiara', 2),
  ('Hafiz Zulkifli', 1900000, 'Mont Kiara', 1),
  ('Samantha Goh', 3600000, 'KLCC', 2),
  ('Bernard Heng', 7200000, 'Damansara Heights', 3),
  ('Deepak Sethi', 1400000, 'Desa ParkCity', 1),
  ('Liyana Yusof', 2900000, 'Bangsar', 2),
  ('Kenneth Ooi', 950000, 'Taman Desa', 0),
  ('Fazura Sharif', 5200000, 'Mont Kiara', 4),
  ('Desmond Tay', 4400000, 'KLCC', 3),
  ('Suresh Menon', 1750000, 'Desa ParkCity', 1),
  ('Hannah Yeoh', 3300000, 'Bangsar', 2),
  ('Rizal Ramli', 2400000, 'Mont Kiara', 1),
  ('Joanne Phoon', 6800000, 'Damansara Heights', 5);

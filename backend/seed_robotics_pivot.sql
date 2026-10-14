-- =============================================================================
-- PIPELINE.EV Seed Data: Industrial Robotics Pivot
-- Run in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/tppzkfhhcnmdbwnamgqr/sql/new
-- =============================================================================

-- Relax legacy real-estate constraints if present
alter table properties drop constraint if exists properties_property_type_check;
alter table properties drop constraint if exists properties_status_check;
alter table properties drop constraint if exists properties_listing_status_check;
alter table properties add column if not exists listing_status text default 'available';

alter table clients drop constraint if exists clients_financing_status_check;
alter table clients add constraint clients_financing_status_check 
  check (financing_status is null or financing_status in ('cash', 'pre-approved', 'in-progress', 'unspecified', 'leasing'));
alter table clients drop constraint if exists clients_property_type_preference_check;

-- Wipe existing seed data (keep schema, tables, all other structures intact)
truncate properties, clients, pipeline_evaluations, invite_drafts, reasoning_cache,
  scheduled_viewings, signals, client_past_purchases cascade;

-- Ensure agent roles reflect sales rep naming
update agents set role = 'Senior Sales Rep' where initials = 'RD';
update agents set role = 'Sales Rep' where initials in ('SY', 'AR');

-- ── 1. ROBOT UNITS (20 Units) ────────────────────────────────────────────────
-- property_value = unit cost (CapEx in RM)
-- neighborhood   = target environment / industry
-- bedrooms       = payload tier (repurposed as numeric payload rating 1–5)
-- bathrooms      = navigation redundancy count (sensors/lidar redundancy 1–4)
-- sqft           = operational range (coverage sq ft per 8h shift)
-- property_type  = robot category (AMR, Cobot, Service Robot, Drone, AgTech, etc.)
-- status         = 'LISTED' (listing_status = 'available')

insert into properties (address, neighborhood, property_value, bedrooms, bathrooms, sqft, property_type, status, listing_status, image_url) values
  ('AMR-4000 Heavy-Lift Pallet Jack', 'Logistics & Warehousing', 185000, 4, 2, 5000, 'AMR', 'LISTED', 'available', 'https://images.pexels.com/photos/6169056/pexels-photo-6169056.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('MediClean UV-Sanitation Bot', 'Healthcare Facilities', 95000, 2, 3, 1200, 'Service Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('OutdoorScout Perimeter Patrol Unit', 'Outdoor / Industrial Sites', 142000, 3, 4, 8000, 'Security Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/8566472/pexels-photo-8566472.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('FlexArm Assembly Cobot', 'Manufacturing', 78000, 1, 2, 400, 'Cobot', 'LISTED', 'available', 'https://images.pexels.com/photos/3912953/pexels-photo-3912953.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('CleanSweep Retail Floor Bot', 'Retail & Commercial', 42000, 1, 2, 3000, 'Service Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/3825586/pexels-photo-3825586.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('SkyView Inventory Drone', 'Logistics & Warehousing', 61000, 1, 1, 15000, 'Drone', 'LISTED', 'available', 'https://images.pexels.com/photos/1034812/pexels-photo-1034812.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('AgroHarvest Picker Bot', 'Agriculture & Forestry', 115000, 2, 2, 6000, 'AgTech Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/2582818/pexels-photo-2582818.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('WeldMaster Heavy Gantry Unit', 'Manufacturing', 210000, 5, 3, 800, 'Industrial Arm', 'LISTED', 'available', 'https://images.pexels.com/photos/1267338/pexels-photo-1267338.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('SortX High-Speed Sorter', 'Logistics & Warehousing', 135000, 2, 2, 4500, 'AMR', 'LISTED', 'available', 'https://images.pexels.com/photos/4481259/pexels-photo-4481259.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('SteriRoom Mobile Decon Unit', 'Healthcare Facilities', 88000, 2, 2, 900, 'Service Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/7089018/pexels-photo-7089018.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('ThermoGuard Cold-Chain Runner', 'Logistics & Warehousing', 155000, 3, 3, 7000, 'AMR', 'LISTED', 'available', 'https://images.pexels.com/photos/6169052/pexels-photo-6169052.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('PrecisionWeld Cobot Cell', 'Manufacturing', 175000, 4, 2, 500, 'Cobot', 'LISTED', 'available', 'https://images.pexels.com/photos/3825539/pexels-photo-3825539.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('ShelfScout RFID Audit Rover', 'Retail & Commercial', 49000, 1, 2, 12000, 'Service Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/264636/pexels-photo-264636.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('FieldCrop Autonomous Sprayer', 'Agriculture & Forestry', 128000, 3, 2, 25000, 'AgTech Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/2132171/pexels-photo-2132171.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('YardMaster Autonomous Tug', 'Outdoor / Industrial Sites', 198000, 5, 4, 18000, 'Heavy AMR', 'LISTED', 'available', 'https://images.pexels.com/photos/2226458/pexels-photo-2226458.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('PharmaBot Dispense & Transport', 'Healthcare Facilities', 112000, 2, 3, 1500, 'Service Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/3786157/pexels-photo-3786157.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('MicroAssembly Delta Cell', 'Manufacturing', 68000, 1, 2, 300, 'Delta Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/256381/pexels-photo-256381.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('AeroPatrol Surveillance Drone', 'Outdoor / Industrial Sites', 82000, 1, 3, 30000, 'Drone', 'LISTED', 'available', 'https://images.pexels.com/photos/1034812/pexels-photo-1034812.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('CartRunner Supermarket Replenisher', 'Retail & Commercial', 54000, 2, 2, 4000, 'AMR', 'LISTED', 'available', 'https://images.pexels.com/photos/264507/pexels-photo-264507.jpeg?auto=compress&cs=tinysrgb&w=800'),
  ('BioGreen Canopy Pruner', 'Agriculture & Forestry', 105000, 2, 2, 8500, 'AgTech Robot', 'LISTED', 'available', 'https://images.pexels.com/photos/2886937/pexels-photo-2886937.jpeg?auto=compress&cs=tinysrgb&w=800');

-- Assign units evenly across the 3 sales reps
with numbered_props as (
  select id, row_number() over (order by address) as rn from properties
),
numbered_agents as (
  select id, row_number() over (order by name) as arn, count(*) over () as acnt from agents
)
update properties p
set assigned_agent_id = a.id
from numbered_props np
join numbered_agents a on ((np.rn % a.acnt) + 1) = a.arn
where p.id = np.id;

-- ── 2. COMPANIES / FACILITIES (50 Companies) ─────────────────────────────────
-- stated_budget          = procurement budget (RM)
-- preferred_neighborhood = target industry / environment
-- past_viewings          = demo sessions attended (0–5)
-- financing_status       = 'leasing' | 'pre-approved' | 'cash' | 'in-progress' | 'unspecified'
-- agent_notes            = operational notes / automation ROI driver

insert into clients (name, stated_budget, preferred_neighborhood, past_viewings, financing_status, relationship_stage, agent_notes) values
  ('Nordic Freight Solutions', 900000, 'Logistics & Warehousing', 3, 'leasing', 'new', 'Q3 throughput bottleneck, evaluating automation ROI for main distribution center'),
  ('Regional Medical Center Group', 450000, 'Healthcare Facilities', 1, 'pre-approved', 'new', 'Infection control compliance and pathogen reduction driving sterilization purchase'),
  ('Titan Manufacturing Corp', 320000, 'Manufacturing', 5, 'cash', 'new', 'Labor shortage on precision assembly line; fast-track deployment priority'),
  ('Coastal Retail Group', 180000, 'Retail & Commercial', 0, 'unspecified', 'new', 'Evaluating automated shelf audit across 12 hypermarket locations'),
  ('Apex Express Logistics', 650000, 'Logistics & Warehousing', 4, 'cash', 'new', 'Expanding cross-dock hub capacity; requires heavy-payload AMRs'),
  ('Southern Health Consortium', 380000, 'Healthcare Facilities', 2, 'pre-approved', 'new', 'Targeting autonomous sterile supply transfer across inpatient wards'),
  ('Kinetic Precision Machining', 290000, 'Manufacturing', 3, 'in-progress', 'new', 'CNC machine tending automation required for second shift operation'),
  ('MegaMart Distribution Hub', 520000, 'Retail & Commercial', 2, 'leasing', 'new', 'High aisle congestion during daytime replenishment cycles'),
  ('GreenValley Agro Farms', 340000, 'Agriculture & Forestry', 2, 'cash', 'new', 'Seasonal picker shortage; testing orchard harvesting units'),
  ('Portside Terminal Operations', 850000, 'Outdoor / Industrial Sites', 4, 'pre-approved', 'new', 'Yard container inspection and perimeter patrol coverage requirements'),
  ('Pacific Cold Storage Logistics', 420000, 'Logistics & Warehousing', 3, 'leasing', 'new', 'Sub-zero frozen warehouse operations; human shift limits require automation'),
  ('St. Jude Metropolitan Hospital', 280000, 'Healthcare Facilities', 1, 'in-progress', 'new', 'Bio-hazard waste delivery route automation project'),
  ('Vanguard Heavy Fabrication', 720000, 'Manufacturing', 4, 'cash', 'new', 'Automated gantry welding needed for structural steel joints'),
  ('Urban Grocery Express', 140000, 'Retail & Commercial', 1, 'unspecified', 'new', 'Micro-fulfillment center automated order staging evaluation'),
  ('Highland Tea & Crop Estates', 260000, 'Agriculture & Forestry', 1, 'leasing', 'new', 'Steep slope terrain spraying and crop monitoring drone feasibility'),
  ('Apex Petrochemical Complex', 950000, 'Outdoor / Industrial Sites', 5, 'cash', 'new', 'ATEX zone perimeter and gas leak autonomous drone patrol'),
  ('SwiftParcel Fulfillment Hub', 310000, 'Logistics & Warehousing', 2, 'pre-approved', 'new', 'High parcel rejection rates; requires automated sorting integration'),
  ('Premier Surgical Institute', 220000, 'Healthcare Facilities', 0, 'unspecified', 'new', 'Autonomous OR instrument kit delivery trial'),
  ('Delta Electronics Assembly', 480000, 'Manufacturing', 3, 'cash', 'new', 'SMT line PCB handling and inspection cobot integration'),
  ('SuperMart Hypermarket Chain', 160000, 'Retail & Commercial', 1, 'leasing', 'new', 'Overnight autonomous floor scrubbing pilot across 8 branches'),
  ('Sunway AgriTech Orchards', 390000, 'Agriculture & Forestry', 3, 'pre-approved', 'new', 'Automated canopy disease identification and targeted spraying'),
  ('Harborview Heavy Cargo Depot', 680000, 'Outdoor / Industrial Sites', 3, 'in-progress', 'new', 'Tug automation for heavy trailer shuttles between dock and staging'),
  ('OmniChannel 3PL Services', 580000, 'Logistics & Warehousing', 4, 'cash', 'new', 'E-commerce peak season order packing and sorting bottleneck'),
  ('General Care Clinic Network', 150000, 'Healthcare Facilities', 0, 'unspecified', 'new', 'Decentralized clinic sanitation automation exploration'),
  ('AutoParts Stamping & Tooling', 410000, 'Manufacturing', 2, 'leasing', 'new', 'Metal press tending safety compliance upgrade'),
  ('FreshFoods Central Distribution', 240000, 'Retail & Commercial', 2, 'pre-approved', 'new', 'Temperature-controlled grocery staging AMR evaluation'),
  ('Borno Agro Industrial Plantation', 820000, 'Agriculture & Forestry', 4, 'cash', 'new', 'Large scale autonomous sprayer deployment for 2,000 hectare estate'),
  ('SecureSite Industrial Park', 360000, 'Outdoor / Industrial Sites', 2, 'leasing', 'new', 'Night-shift remote security patrol to reduce guard post overhead'),
  ('Klang Valley Logistics City', 1100000, 'Logistics & Warehousing', 5, 'cash', 'new', 'Flagship automated mega-depot; multi-fleet pallet jack tender'),
  ('Columbia Medical Centre', 330000, 'Healthcare Facilities', 2, 'pre-approved', 'new', 'Automated inpatient pharmacy dispensing and cart delivery'),
  ('Proton Metal Works', 540000, 'Manufacturing', 3, 'in-progress', 'new', 'Body shop seam welding automation phase 2'),
  ('Metro Department Store Group', 120000, 'Retail & Commercial', 0, 'unspecified', 'new', 'Off-hours inventory count automation inquiry'),
  ('Valley BioAgri Research', 210000, 'Agriculture & Forestry', 1, 'leasing', 'new', 'Field phenotyping automated robotic sensor platform'),
  ('Jurong Offshore Logistics Yard', 790000, 'Outdoor / Industrial Sites', 3, 'cash', 'new', 'Heavy pipe and spool autonomous transport unit evaluation'),
  ('TransAsia Global Express', 880000, 'Logistics & Warehousing', 4, 'pre-approved', 'new', 'Cross-border air cargo sortation and pallet breakdown AMR deployment'),
  ('Pantai Specialist Hospital', 190000, 'Healthcare Facilities', 1, 'in-progress', 'new', 'Hospital room rapid disinfection between patient turnovers'),
  ('Precision Micro-Mechanics', 270000, 'Manufacturing', 2, 'cash', 'new', 'High-mix low-volume medical component assembly cobot cell'),
  ('TrendRetail Fashion Distribution', 200000, 'Retail & Commercial', 1, 'leasing', 'new', 'Automated garment hanging transport between sorting lines'),
  ('EcoFarm Hydroponic Towers', 170000, 'Agriculture & Forestry', 0, 'unspecified', 'new', 'Indoor vertical farm harvesting automation assessment'),
  ('Alliance Quarry & Cement Works', 460000, 'Outdoor / Industrial Sites', 2, 'in-progress', 'new', 'Conveyor perimeter inspection and autonomous dust suppression'),
  ('Nexus E-Commerce Gateway', 620000, 'Logistics & Warehousing', 3, 'cash', 'new', 'Returns processing and restocking autonomous cart project'),
  ('Beacon Hospital Oncology Center', 310000, 'Healthcare Facilities', 2, 'pre-approved', 'new', 'Cleanroom radiation shielding medication transport unit'),
  ('AeroStructures Precision Ltd', 640000, 'Manufacturing', 4, 'cash', 'new', 'Aerospace composite drilling and rivet cobot tooling'),
  ('Kinabalu Mining & Quarry Corp', 35000, 'Underground Mining & Tunneling', 0, 'unspecified', 'new', 'Sub-surface explosive tunneling drill automation inquiry; catalog lacks ATEX underground certification'),
  ('Nusantara Deepwater Subsea', 40000, 'Deepwater Offshore & Subsea', 0, 'unspecified', 'new', 'Offshore deepwater pipeline crawler requested; standard catalog units cannot operate pressurized underwater'),
  ('PetroChemical HazMat Labs', 30000, 'Hazardous ATEX Zone 0 Labs', 0, 'unspecified', 'new', 'Volatile gas handling robot requirement; requires intrinsic safety rating not supported by commercial fleet'),
  ('Highland Eco-Artisans', 18000, 'Artisan Handcrafts & Woodwork', 0, 'unspecified', 'new', 'Bespoke custom carving studio; budget is far below industrial robotic manipulators'),
  ('Island Marine Salvage', 28000, 'Marine & Coastal Salvage', 0, 'unspecified', 'new', 'Saltwater submerged debris recovery; catalog models lack IP68 marinization'),
  ('Metro Micro-Bakery Co', 22000, 'Micro-Food Production', 0, 'unspecified', 'new', 'Small artisanal bakery kitchen; tight workspace and low budget preclude industrial SCARA arms'),
  ('Rural Smallholder Co-op', 20000, 'Smallholder Handcrafts', 0, 'unspecified', 'new', 'Rural cooperative handcraft processing; capital expenditure ceiling too low for entry-level automation');

-- Assign companies evenly across the 3 sales reps
with numbered_clients as (
  select id, row_number() over (order by name) as rn from clients
),
numbered_agents as (
  select id, row_number() over (order by name) as arn, count(*) over () as acnt from agents
)
update clients c
set assigned_agent_id = a.id
from numbered_clients nc
join numbered_agents a on ((nc.rn % a.acnt) + 1) = a.arn
where c.id = nc.id;

-- -----------------------------------------------------------------------------
-- Seed complete! Now call POST /api/run_evaluations to recalculate pipeline scores.
-- -----------------------------------------------------------------------------

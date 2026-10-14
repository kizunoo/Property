"""
apply_robotics_seed.py
-----------------------
Directly populates Supabase with the 20 Robot Units and 50 Companies,
assigns sales reps, and triggers evaluation recalculation.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env or .env.local")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

PROPERTIES_DATA = [
  {"address": "AMR-4000 Heavy-Lift Pallet Jack", "neighborhood": "Logistics & Warehousing", "property_value": 185000, "bedrooms": 4, "bathrooms": 2, "sqft": 5000, "property_type": "AMR", "status": "LISTED", "image_url": "https://images.pexels.com/photos/6169056/pexels-photo-6169056.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "MediClean UV-Sanitation Bot", "neighborhood": "Healthcare Facilities", "property_value": 95000, "bedrooms": 2, "bathrooms": 3, "sqft": 1200, "property_type": "Service Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "OutdoorScout Perimeter Patrol Unit", "neighborhood": "Outdoor / Industrial Sites", "property_value": 142000, "bedrooms": 3, "bathrooms": 4, "sqft": 8000, "property_type": "Security Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/8566472/pexels-photo-8566472.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "FlexArm Assembly Cobot", "neighborhood": "Manufacturing", "property_value": 78000, "bedrooms": 1, "bathrooms": 2, "sqft": 400, "property_type": "Cobot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/3912953/pexels-photo-3912953.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "CleanSweep Retail Floor Bot", "neighborhood": "Retail & Commercial", "property_value": 42000, "bedrooms": 1, "bathrooms": 2, "sqft": 3000, "property_type": "Service Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/3825586/pexels-photo-3825586.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "SkyView Inventory Drone", "neighborhood": "Logistics & Warehousing", "property_value": 61000, "bedrooms": 1, "bathrooms": 1, "sqft": 15000, "property_type": "Drone", "status": "LISTED", "image_url": "https://images.pexels.com/photos/1034812/pexels-photo-1034812.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "AgroHarvest Picker Bot", "neighborhood": "Agriculture & Forestry", "property_value": 115000, "bedrooms": 2, "bathrooms": 2, "sqft": 6000, "property_type": "AgTech Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/2582818/pexels-photo-2582818.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "WeldMaster Heavy Gantry Unit", "neighborhood": "Manufacturing", "property_value": 210000, "bedrooms": 5, "bathrooms": 3, "sqft": 800, "property_type": "Industrial Arm", "status": "LISTED", "image_url": "https://images.pexels.com/photos/1267338/pexels-photo-1267338.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "SortX High-Speed Sorter", "neighborhood": "Logistics & Warehousing", "property_value": 135000, "bedrooms": 2, "bathrooms": 2, "sqft": 4500, "property_type": "AMR", "status": "LISTED", "image_url": "https://images.pexels.com/photos/4481259/pexels-photo-4481259.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "SteriRoom Mobile Decon Unit", "neighborhood": "Healthcare Facilities", "property_value": 88000, "bedrooms": 2, "bathrooms": 2, "sqft": 900, "property_type": "Service Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/7089018/pexels-photo-7089018.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "ThermoGuard Cold-Chain Runner", "neighborhood": "Logistics & Warehousing", "property_value": 155000, "bedrooms": 3, "bathrooms": 3, "sqft": 7000, "property_type": "AMR", "status": "LISTED", "image_url": "https://images.pexels.com/photos/6169052/pexels-photo-6169052.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "PrecisionWeld Cobot Cell", "neighborhood": "Manufacturing", "property_value": 175000, "bedrooms": 4, "bathrooms": 2, "sqft": 500, "property_type": "Cobot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/3825539/pexels-photo-3825539.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "ShelfScout RFID Audit Rover", "neighborhood": "Retail & Commercial", "property_value": 49000, "bedrooms": 1, "bathrooms": 2, "sqft": 12000, "property_type": "Service Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/264636/pexels-photo-264636.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "FieldCrop Autonomous Sprayer", "neighborhood": "Agriculture & Forestry", "property_value": 128000, "bedrooms": 3, "bathrooms": 2, "sqft": 25000, "property_type": "AgTech Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/2132171/pexels-photo-2132171.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "YardMaster Autonomous Tug", "neighborhood": "Outdoor / Industrial Sites", "property_value": 198000, "bedrooms": 5, "bathrooms": 4, "sqft": 18000, "property_type": "Heavy AMR", "status": "LISTED", "image_url": "https://images.pexels.com/photos/2226458/pexels-photo-2226458.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "PharmaBot Dispense & Transport", "neighborhood": "Healthcare Facilities", "property_value": 112000, "bedrooms": 2, "bathrooms": 3, "sqft": 1500, "property_type": "Service Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/3786157/pexels-photo-3786157.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "MicroAssembly Delta Cell", "neighborhood": "Manufacturing", "property_value": 68000, "bedrooms": 1, "bathrooms": 2, "sqft": 300, "property_type": "Delta Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/256381/pexels-photo-256381.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "AeroPatrol Surveillance Drone", "neighborhood": "Outdoor / Industrial Sites", "property_value": 82000, "bedrooms": 1, "bathrooms": 3, "sqft": 30000, "property_type": "Drone", "status": "LISTED", "image_url": "https://images.pexels.com/photos/1034812/pexels-photo-1034812.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "CartRunner Supermarket Replenisher", "neighborhood": "Retail & Commercial", "property_value": 54000, "bedrooms": 2, "bathrooms": 2, "sqft": 4000, "property_type": "AMR", "status": "LISTED", "image_url": "https://images.pexels.com/photos/264507/pexels-photo-264507.jpeg?auto=compress&cs=tinysrgb&w=800"},
  {"address": "BioGreen Canopy Pruner", "neighborhood": "Agriculture & Forestry", "property_value": 105000, "bedrooms": 2, "bathrooms": 2, "sqft": 8500, "property_type": "AgTech Robot", "status": "LISTED", "image_url": "https://images.pexels.com/photos/2886937/pexels-photo-2886937.jpeg?auto=compress&cs=tinysrgb&w=800"}
]

CLIENTS_DATA = [
  {"name": "Nordic Freight Solutions", "stated_budget": 900000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 3, "financing_status": "in-progress", "relationship_stage": "evaluating", "agent_notes": "Q3 throughput bottleneck, evaluating automation ROI for main distribution center"},
  {"name": "Regional Medical Center Group", "stated_budget": 450000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 1, "financing_status": "pre-approved", "relationship_stage": "negotiating", "agent_notes": "Infection control compliance and pathogen reduction driving sterilization purchase"},
  {"name": "Titan Manufacturing Corp", "stated_budget": 320000, "preferred_neighborhood": "Manufacturing", "past_viewings": 5, "financing_status": "cash", "relationship_stage": "closing", "agent_notes": "Labor shortage on precision assembly line; fast-track deployment priority"},
  {"name": "Coastal Retail Group", "stated_budget": 180000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Evaluating automated shelf audit across 12 hypermarket locations"},
  {"name": "Apex Express Logistics", "stated_budget": 650000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 4, "financing_status": "cash", "relationship_stage": "closing", "agent_notes": "Expanding cross-dock hub capacity; requires heavy-payload AMRs"},
  {"name": "Southern Health Consortium", "stated_budget": 380000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 2, "financing_status": "pre-approved", "relationship_stage": "evaluating", "agent_notes": "Targeting autonomous sterile supply transfer across inpatient wards"},
  {"name": "Kinetic Precision Machining", "stated_budget": 290000, "preferred_neighborhood": "Manufacturing", "past_viewings": 3, "financing_status": "in-progress", "relationship_stage": "evaluating", "agent_notes": "CNC machine tending automation required for second shift operation"},
  {"name": "MegaMart Distribution Hub", "stated_budget": 520000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 2, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "High aisle congestion during daytime replenishment cycles"},
  {"name": "GreenValley Agro Farms", "stated_budget": 340000, "preferred_neighborhood": "Agriculture & Forestry", "past_viewings": 2, "financing_status": "cash", "relationship_stage": "evaluating", "agent_notes": "Seasonal picker shortage; testing orchard harvesting units"},
  {"name": "Portside Terminal Operations", "stated_budget": 850000, "preferred_neighborhood": "Outdoor / Industrial Sites", "past_viewings": 4, "financing_status": "pre-approved", "relationship_stage": "negotiating", "agent_notes": "Yard container inspection and perimeter patrol coverage requirements"},
  {"name": "Pacific Cold Storage Logistics", "stated_budget": 420000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 3, "financing_status": "in-progress", "relationship_stage": "evaluating", "agent_notes": "Sub-zero frozen warehouse operations; human shift limits require automation"},
  {"name": "St. Jude Metropolitan Hospital", "stated_budget": 280000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 1, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Bio-hazard waste delivery route automation project"},
  {"name": "Vanguard Heavy Fabrication", "stated_budget": 720000, "preferred_neighborhood": "Manufacturing", "past_viewings": 4, "financing_status": "cash", "relationship_stage": "negotiating", "agent_notes": "Automated gantry welding needed for structural steel joints"},
  {"name": "Urban Grocery Express", "stated_budget": 140000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 1, "financing_status": "unspecified", "relationship_stage": "contacted", "agent_notes": "Micro-fulfillment center automated order staging evaluation"},
  {"name": "Highland Tea & Crop Estates", "stated_budget": 260000, "preferred_neighborhood": "Agriculture & Forestry", "past_viewings": 1, "financing_status": "in-progress", "relationship_stage": "new", "agent_notes": "Steep slope terrain spraying and crop monitoring drone feasibility"},
  {"name": "Apex Petrochemical Complex", "stated_budget": 950000, "preferred_neighborhood": "Outdoor / Industrial Sites", "past_viewings": 5, "financing_status": "cash", "relationship_stage": "closing", "agent_notes": "ATEX zone perimeter and gas leak autonomous drone patrol"},
  {"name": "SwiftParcel Fulfillment Hub", "stated_budget": 310000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 2, "financing_status": "pre-approved", "relationship_stage": "evaluating", "agent_notes": "High parcel rejection rates; requires automated sorting integration"},
  {"name": "Premier Surgical Institute", "stated_budget": 220000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Autonomous OR instrument kit delivery trial"},
  {"name": "Delta Electronics Assembly", "stated_budget": 480000, "preferred_neighborhood": "Manufacturing", "past_viewings": 3, "financing_status": "cash", "relationship_stage": "negotiating", "agent_notes": "SMT line PCB handling and inspection cobot integration"},
  {"name": "SuperMart Hypermarket Chain", "stated_budget": 160000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 1, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Overnight autonomous floor scrubbing pilot across 8 branches"},
  {"name": "Sunway AgriTech Orchards", "stated_budget": 390000, "preferred_neighborhood": "Agriculture & Forestry", "past_viewings": 3, "financing_status": "pre-approved", "relationship_stage": "evaluating", "agent_notes": "Automated canopy disease identification and targeted spraying"},
  {"name": "Harborview Heavy Cargo Depot", "stated_budget": 680000, "preferred_neighborhood": "Outdoor / Industrial Sites", "past_viewings": 3, "financing_status": "in-progress", "relationship_stage": "evaluating", "agent_notes": "Tug automation for heavy trailer shuttles between dock and staging"},
  {"name": "OmniChannel 3PL Services", "stated_budget": 580000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 4, "financing_status": "cash", "relationship_stage": "negotiating", "agent_notes": "E-commerce peak season order packing and sorting bottleneck"},
  {"name": "General Care Clinic Network", "stated_budget": 150000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Decentralized clinic sanitation automation exploration"},
  {"name": "AutoParts Stamping & Tooling", "stated_budget": 410000, "preferred_neighborhood": "Manufacturing", "past_viewings": 2, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Metal press tending safety compliance upgrade"},
  {"name": "FreshFoods Central Distribution", "stated_budget": 240000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 2, "financing_status": "pre-approved", "relationship_stage": "evaluating", "agent_notes": "Temperature-controlled grocery staging AMR evaluation"},
  {"name": "Borno Agro Industrial Plantation", "stated_budget": 820000, "preferred_neighborhood": "Agriculture & Forestry", "past_viewings": 4, "financing_status": "cash", "relationship_stage": "negotiating", "agent_notes": "Large scale autonomous sprayer deployment for 2,000 hectare estate"},
  {"name": "SecureSite Industrial Park", "stated_budget": 360000, "preferred_neighborhood": "Outdoor / Industrial Sites", "past_viewings": 2, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Night-shift remote security patrol to reduce guard post overhead"},
  {"name": "Klang Valley Logistics City", "stated_budget": 1100000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 5, "financing_status": "cash", "relationship_stage": "closing", "agent_notes": "Flagship automated mega-depot; multi-fleet pallet jack tender"},
  {"name": "Columbia Medical Centre", "stated_budget": 330000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 2, "financing_status": "pre-approved", "relationship_stage": "evaluating", "agent_notes": "Automated inpatient pharmacy dispensing and cart delivery"},
  {"name": "Proton Metal Works", "stated_budget": 540000, "preferred_neighborhood": "Manufacturing", "past_viewings": 3, "financing_status": "in-progress", "relationship_stage": "evaluating", "agent_notes": "Body shop seam welding automation phase 2"},
  {"name": "Metro Department Store Group", "stated_budget": 120000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Off-hours inventory count automation inquiry"},
  {"name": "Valley BioAgri Research", "stated_budget": 210000, "preferred_neighborhood": "Agriculture & Forestry", "past_viewings": 1, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Field phenotyping automated robotic sensor platform"},
  {"name": "Jurong Offshore Logistics Yard", "stated_budget": 790000, "preferred_neighborhood": "Outdoor / Industrial Sites", "past_viewings": 3, "financing_status": "cash", "relationship_stage": "evaluating", "agent_notes": "Heavy pipe and spool autonomous transport unit evaluation"},
  {"name": "TransAsia Global Express", "stated_budget": 880000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 4, "financing_status": "pre-approved", "relationship_stage": "closing", "agent_notes": "Cross-border air cargo sortation and pallet breakdown AMR deployment"},
  {"name": "Pantai Specialist Hospital", "stated_budget": 190000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 1, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Hospital room rapid disinfection between patient turnovers"},
  {"name": "Precision Micro-Mechanics", "stated_budget": 270000, "preferred_neighborhood": "Manufacturing", "past_viewings": 2, "financing_status": "cash", "relationship_stage": "evaluating", "agent_notes": "High-mix low-volume medical component assembly cobot cell"},
  {"name": "TrendRetail Fashion Distribution", "stated_budget": 200000, "preferred_neighborhood": "Retail & Commercial", "past_viewings": 1, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Automated garment hanging transport between sorting lines"},
  {"name": "EcoFarm Hydroponic Towers", "stated_budget": 170000, "preferred_neighborhood": "Agriculture & Forestry", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Indoor vertical farm harvesting automation assessment"},
  {"name": "Alliance Quarry & Cement Works", "stated_budget": 460000, "preferred_neighborhood": "Outdoor / Industrial Sites", "past_viewings": 2, "financing_status": "in-progress", "relationship_stage": "contacted", "agent_notes": "Conveyor perimeter inspection and autonomous dust suppression"},
  {"name": "Nexus E-Commerce Gateway", "stated_budget": 620000, "preferred_neighborhood": "Logistics & Warehousing", "past_viewings": 3, "financing_status": "cash", "relationship_stage": "evaluating", "agent_notes": "Returns processing and restocking autonomous cart project"},
  {"name": "Beacon Hospital Oncology Center", "stated_budget": 310000, "preferred_neighborhood": "Healthcare Facilities", "past_viewings": 2, "financing_status": "pre-approved", "relationship_stage": "evaluating", "agent_notes": "Cleanroom radiation shielding medication transport unit"},
  {"name": "AeroStructures Precision Ltd", "stated_budget": 640000, "preferred_neighborhood": "Manufacturing", "past_viewings": 4, "financing_status": "cash", "relationship_stage": "closing", "agent_notes": "Aerospace composite drilling and rivet cobot tooling"},
  {"name": "Kinabalu Mining & Quarry Corp", "stated_budget": 35000, "preferred_neighborhood": "Underground Mining & Tunneling", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Sub-surface explosive tunneling drill automation inquiry; catalog lacks ATEX underground certification"},
  {"name": "Nusantara Deepwater Subsea", "stated_budget": 40000, "preferred_neighborhood": "Deepwater Offshore & Subsea", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Offshore deepwater pipeline crawler requested; standard catalog units cannot operate pressurized underwater"},
  {"name": "PetroChemical HazMat Labs", "stated_budget": 30000, "preferred_neighborhood": "Hazardous ATEX Zone 0 Labs", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Volatile gas handling robot requirement; requires intrinsic safety rating not supported by commercial fleet"},
  {"name": "Highland Eco-Artisans", "stated_budget": 18000, "preferred_neighborhood": "Artisan Handcrafts & Woodwork", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Bespoke custom carving studio; budget is far below industrial robotic manipulators"},
  {"name": "Island Marine Salvage", "stated_budget": 28000, "preferred_neighborhood": "Marine & Coastal Salvage", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Saltwater submerged debris recovery; catalog models lack IP68 marinization"},
  {"name": "Metro Micro-Bakery Co", "stated_budget": 22000, "preferred_neighborhood": "Micro-Food Production", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Small artisanal bakery kitchen; tight workspace and low budget preclude industrial SCARA arms"},
  {"name": "Rural Smallholder Co-op", "stated_budget": 20000, "preferred_neighborhood": "Smallholder Handcrafts", "past_viewings": 0, "financing_status": "unspecified", "relationship_stage": "new", "agent_notes": "Rural cooperative handcraft processing; capital expenditure ceiling too low for entry-level automation"}
]


def apply_seed():
    print("1. Fetching sales reps...")
    agents = supabase.table("agents").select("id, initials, name").execute().data or []
    agent_ids = [a["id"] for a in agents]
    print(f"Found {len(agent_ids)} agents: {[a['initials'] for a in agents]}")

    print("2. Cleaning dependent tables...")
    for tbl in ["scheduled_viewings", "invite_drafts", "reasoning_cache", "signals", "client_past_purchases", "pipeline_evaluations"]:
        try:
            supabase.table(tbl).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            print(f"Cleared {tbl}")
        except Exception as e:
            print(f"Notice on {tbl}: {e}")

    print("3. Clearing properties and clients...")
    supabase.table("properties").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    supabase.table("clients").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("Cleared properties and clients.")

    print("4. Inserting 20 Robot Units...")
    for idx, prop in enumerate(PROPERTIES_DATA):
        p_row = {**prop}
        if agent_ids:
            p_row["assigned_agent_id"] = agent_ids[idx % len(agent_ids)]
        try:
            supabase.table("properties").insert(p_row).execute()
        except Exception as exc:
            # Fallback if property_type constraint is still active in Postgres
            if "properties_property_type_check" in str(exc):
                p_row["property_type"] = None
                supabase.table("properties").insert(p_row).execute()
            else:
                raise exc
    print("20 Robot Units inserted.")

    print("5. Inserting 50 Companies...")
    for idx, client in enumerate(CLIENTS_DATA):
        c_row = {**client}
        if agent_ids:
            c_row["assigned_agent_id"] = agent_ids[idx % len(agent_ids)]
        # All freshly seeded prospects start strictly in the 'new' stage
        c_row["relationship_stage"] = "new"

        try:
            supabase.table("clients").insert(c_row).execute()
        except Exception as exc:
            if "clients_financing_status_check" in str(exc):
                c_row["financing_status"] = "in-progress"
                supabase.table("clients").insert(c_row).execute()
            else:
                raise exc
    print("50 Companies inserted.")

    p_count = supabase.table("properties").select("id", count="exact").execute().count
    c_count = supabase.table("clients").select("id", count="exact").execute().count
    print(f"Verification: {p_count} properties (robots), {c_count} clients (companies) in database.")


if __name__ == "__main__":
    apply_seed()

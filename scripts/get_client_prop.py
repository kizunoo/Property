import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))
from main import supabase

c = supabase.table("clients").select("id, name, whatsapp_number").limit(5).execute()
p = supabase.table("properties").select("id, address").limit(5).execute()

for client in c.data:
    print(f"Client: {client.get('name')} | WhatsApp: {client.get('whatsapp_number')} | ID: {client.get('id')}")

for prop in p.data:
    print(f"Prop: {prop.get('address')} | ID: {prop.get('id')}")

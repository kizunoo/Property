import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))
from main import supabase

convs = supabase.table("whatsapp_conversations").select("*").eq("phone_number", "60109722730").execute()
print("Conversations for 60109722730:", len(convs.data))
if convs.data:
    for c in convs.data:
        print(c)

msgs = supabase.table("whatsapp_messages").select("*").eq("phone_number", "60109722730").order("created_at", desc=True).limit(5).execute()
print("Messages count:", len(msgs.data))
for m in msgs.data:
    print(m.get("sender"), "|", m.get("text"), "|", m.get("created_at"))

import socket

TARGETS = [
    ("aws-0-us-east-1.pooler.supabase.com", 5432, "Supabase session pooler"),
    ("aws-0-us-east-1.pooler.supabase.com", 6543, "Supabase transaction pooler"),
    ("db.eihklkjyrywaalwuerv.supabase.co", 5432, "Supabase direct connection"),
    ("aws-0-us-east-1.pooler.supabase.com", 443, "Same host, standard HTTPS port"),
]

for host, port, label in TARGETS:
    try:
        sock = socket.create_connection((host, port), timeout=8)
        sock.close()
        print(f"OK   {label} ({host}:{port})")
    except Exception as exc:
        print(f"FAIL {label} ({host}:{port}) -> {type(exc).__name__}")
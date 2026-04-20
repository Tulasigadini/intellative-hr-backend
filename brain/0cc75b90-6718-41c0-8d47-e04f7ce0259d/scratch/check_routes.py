from main import app
for route in app.routes:
    print(f"{list(route.methods) if hasattr(route, 'methods') else 'GET'} {route.path}")

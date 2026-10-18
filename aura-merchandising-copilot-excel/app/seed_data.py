"""Excel edition: demo data is already supplied in data/aura_retail_data.xlsx.
Edit the workbook directly instead of seeding SQLite.
"""
from app.excel_store import store
if __name__ == "__main__":
    store.validate()
    print(f"Excel demo data is ready: {store.path}")

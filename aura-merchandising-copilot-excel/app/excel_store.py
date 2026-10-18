from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import pandas as pd
from app.config import EXCEL_FILE

REQUIRED_SHEETS = {
    "Brands": ["brand_id","name","segment","max_discount_percent","minimum_margin_percent"],
    "Products": ["sku","brand_id","product_name","category","sub_category","cost_price","selling_price","launch_date"],
    "Inventory": ["sku","store","current_stock","received_date"],
    "Sales": ["sale_date","sku","store","units_sold","selling_price","discount_percent"],
    "Promotion_Rules": ["brand_id","rule_name","rule_value"],
    "Promotion_History": ["promotion_id","sku","promotion_type","start_date","end_date","units_sold","notes"],
    "Loyalty": ["customer_id","segment","total_spend","visits","points_balance"],
    "Campaign_Results": ["campaign_id","sku","promotion_type","predicted_units","actual_units","predicted_profit","actual_profit"],
}

@dataclass
class BrandRecord:
    brand_id: str
    name: str
    segment: str
    max_discount_percent: float
    minimum_margin_percent: float

@dataclass
class ProductRecord:
    sku: str
    brand_id: str
    product_name: str
    category: str
    sub_category: str
    cost_price: float
    selling_price: float
    launch_date: date

class ExcelStore:
    def __init__(self, path: str | Path = EXCEL_FILE):
        self.path = Path(path)

    def validate(self):
        if not self.path.exists():
            raise FileNotFoundError(f"Excel data file not found: {self.path}")
        book = pd.ExcelFile(self.path, engine="openpyxl")
        missing_sheets = [s for s in REQUIRED_SHEETS if s not in book.sheet_names]
        if missing_sheets:
            raise ValueError(f"Missing Excel sheets: {missing_sheets}")
        for sheet, cols in REQUIRED_SHEETS.items():
            df = pd.read_excel(self.path, sheet_name=sheet, header=2, engine="openpyxl")
            missing = [c for c in cols if c not in df.columns]
            if missing:
                raise ValueError(f"Sheet {sheet} is missing columns: {missing}")
        return True

    def read(self, sheet: str) -> pd.DataFrame:
        if sheet not in REQUIRED_SHEETS:
            raise ValueError(f"Unsupported sheet: {sheet}")
        return pd.read_excel(self.path, sheet_name=sheet, header=2, engine="openpyxl")

    def brands(self):
        df=self.read("Brands").dropna(subset=["brand_id"])
        return [BrandRecord(str(r.brand_id),str(r.name),str(r.segment),float(r.max_discount_percent),float(r.minimum_margin_percent)) for r in df.itertuples(index=False)]

    def brand(self, brand_id: str):
        return next((b for b in self.brands() if b.brand_id == brand_id), None)

    def products(self, brand_id: str | None = None):
        df=self.read("Products").dropna(subset=["sku"])
        if brand_id: df=df[df["brand_id"].astype(str)==brand_id]
        out=[]
        for r in df.itertuples(index=False):
            launch=pd.to_datetime(r.launch_date).date()
            out.append(ProductRecord(str(r.sku),str(r.brand_id),str(r.product_name),str(r.category),str(r.sub_category),float(r.cost_price),float(r.selling_price),launch))
        return out

    def product(self, sku: str):
        return next((p for p in self.products() if p.sku == sku), None)

    def stock(self, sku: str) -> int:
        df=self.read("Inventory")
        vals=pd.to_numeric(df.loc[df["sku"].astype(str)==sku,"current_stock"], errors="coerce").fillna(0)
        return int(vals.sum())

    def last30_units(self, sku: str) -> int:
        df=self.read("Sales")
        df["sale_date"]=pd.to_datetime(df["sale_date"], errors="coerce")
        cutoff=pd.Timestamp(date.today())-pd.Timedelta(days=30)
        vals=pd.to_numeric(df.loc[(df["sku"].astype(str)==sku)&(df["sale_date"]>=cutoff),"units_sold"],errors="coerce").fillna(0)
        return int(vals.sum())

    def inventory_rows(self):
        return self.read("Inventory")

    def sales(self):
        return self.read("Sales")

store=ExcelStore()

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.excel_store import store
from app.engines.dead_stock import dead_stock_report
from app.engines.optimizer import optimize_product
from app.services.ai_service import grounded_answer
from app.config import MAX_CHAT_CHARS, EXCEL_FILE

@asynccontextmanager
async def lifespan(app: FastAPI):
    store.validate()
    yield

app=FastAPI(title="Aura Merchandising Copilot",version="0.2.0",description="Multi-brand retail decision-support prototype using Excel as the primary data source.",lifespan=lifespan)

class OptimizeRequest(BaseModel):
    sku:str=Field(min_length=2,max_length=40); deadline_days:int=Field(default=30,ge=1,le=365); objective:str=Field(default="balanced"); minimum_margin_percent:float|None=Field(default=None,ge=0,le=95); max_discount_percent:float|None=Field(default=None,ge=0,le=80)
    @field_validator("objective")
    @classmethod
    def objective_allowed(cls,v):
        if v not in {"clearance","profit","balanced"}: raise ValueError("objective must be clearance, profit, or balanced")
        return v

class ChatRequest(BaseModel):
    message:str=Field(min_length=1,max_length=MAX_CHAT_CHARS); sku:str|None=Field(default=None,max_length=40); deadline_days:int=Field(default=30,ge=1,le=365); objective:str="balanced"

@app.get("/health")
def health():
    try: store.validate(); excel_ok=True
    except Exception: excel_ok=False
    return {"status":"ok" if excel_ok else "degraded","app":"Aura Merchandising Copilot","data_source":"excel","excel_file":EXCEL_FILE,"excel_valid":excel_ok,"supported_llm_providers":["groq","gemini"],"demo_data":True,"note":"Synthetic demo data. No real campaigns are executed."}

@app.get("/api/brands")
def list_brands():
    return [b.__dict__ for b in store.brands()]

@app.get("/api/products")
def list_products(brand_id:str|None=None):
    result=[]
    for p in store.products(brand_id):
        b=store.brand(p.brand_id)
        result.append({"sku":p.sku,"product_name":p.product_name,"brand":b.name if b else None,"brand_id":p.brand_id,"category":p.category,"cost_price":p.cost_price,"selling_price":p.selling_price,"launch_date":p.launch_date.isoformat(),"current_stock":store.stock(p.sku)})
    return result

@app.get("/api/dead-stock")
def get_dead_stock(): return dead_stock_report(store)

@app.post("/api/optimize")
def optimize(req:OptimizeRequest):
    p=store.product(req.sku)
    if not p: raise HTTPException(404,"SKU not found in the Excel catalog.")
    b=store.brand(p.brand_id); stock=store.stock(req.sku)
    if stock<=0: raise HTTPException(400,"No available stock for this SKU.")
    last30=store.last30_units(req.sku)
    try: result=optimize_product(p,b,stock,max(last30/30,0.1),req.deadline_days,req.objective,req.minimum_margin_percent,req.max_discount_percent)
    except ValueError as exc: raise HTTPException(422,str(exc))
    result["data_basis"]="synthetic demo Excel data"; result["baseline_daily_sales_30d"]=round(last30/30,2)
    return result

@app.post("/api/chat")
def chat(req:ChatRequest):
    context={"demo_data":True,"data_source":"Excel","request":{"deadline_days":req.deadline_days,"objective":req.objective}}
    if req.sku:
        p=store.product(req.sku)
        if not p: raise HTTPException(404,"SKU not found. Choose a SKU from /api/products.")
        b=store.brand(p.brand_id); stock=store.stock(req.sku); last30=store.last30_units(req.sku)
        context["optimization_result"]=optimize_product(p,b,stock,max(last30/30,0.1),req.deadline_days,req.objective)
    context["scope"]="Use only this verified Excel context and retrieved local knowledge. No live company data is connected."
    return grounded_answer(req.message,context)

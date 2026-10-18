from datetime import date
import pandas as pd

def dead_stock_report(store):
    today=date.today(); inv=store.inventory_rows(); sales=store.sales(); sales["sale_date"]=pd.to_datetime(sales["sale_date"],errors="coerce")
    output=[]
    for p in store.products():
        p_inv=inv[inv["sku"].astype(str)==p.sku]
        stock=int(pd.to_numeric(p_inv["current_stock"],errors="coerce").fillna(0).sum())
        store_name=str(p_inv.iloc[0]["store"]) if len(p_inv) else "Unknown"
        ps=sales[sales["sku"].astype(str)==p.sku]
        units=pd.to_numeric(ps["units_sold"],errors="coerce").fillna(0)
        lifetime=int(units.sum())
        cutoff=pd.Timestamp(today)-pd.Timedelta(days=30)
        last30=int(pd.to_numeric(ps.loc[ps["sale_date"]>=cutoff,"units_sold"],errors="coerce").fillna(0).sum())
        age=max(0,(today-p.launch_date).days)
        sell=round(lifetime/(lifetime+stock)*100,2) if lifetime+stock else 0
        daily=last30/30; doh=round(stock/daily,1) if daily>0 else None
        high=age>=60 and last30<30 and sell<70
        output.append({"sku":p.sku,"product_name":p.product_name,"brand_id":p.brand_id,"store":store_name,"current_stock":stock,"stock_age_days":age,"units_sold_last_30_days":last30,"sell_through_percent_proxy":sell,"days_on_hand_estimate":doh,"risk":"high" if high else ("medium" if age>=45 else "low"),"metric_note":"Sell-through is a demo proxy because complete receipts/returns data is not modeled."})
    return sorted(output,key=lambda r:({"high":0,"medium":1,"low":2}[r["risk"]],-r["current_stock"]))

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

# Importing your existing logic modules
from .gee_utils import init_gee, fetch_city_heat_data
from .city_utils import geocode_city, city_buffer_geometry
from .heat_model import build_heat_metrics
from .scenario_model import run_scenarios
from .viz_utils import make_city_map

app = FastAPI()

# Enable CORS so your static frontend can talk to your FastAPI backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SimulationRequest(BaseModel):
    city_name: str
    buffer_km: int
    start_date: str
    end_date: str

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}

@app.post("/api/simulate")
def run_simulation(data: SimulationRequest):
    try:
        init_gee()
        city = geocode_city(data.city_name)
        if city is None:
            raise HTTPException(status_code=404, detail="City not found.")

        region = city_buffer_geometry(city["lat"], city["lon"], data.buffer_km * 1000)
        
        raw_df = fetch_city_heat_data(region, data.start_date, data.end_date, data.city_name)
        
        if raw_df.empty:
            raise HTTPException(status_code=400, detail="No valid surface temperature data found.")

        metrics = build_heat_metrics(raw_df)
        scenario_df = run_scenarios(metrics)

        # Generate Folium map HTML
        folium_map = make_city_map(raw_df)
        map_html = folium_map.get_root().render() if folium_map else ""

        # Convert dataframes / metrics to JSON-serializable dictionaries
        scenarios_dict = scenario_df.to_dict(orient="records")
        
        # Find the best scenario
        best_scenario = scenario_df.sort_values("Cooling reduction (%)", ascending=False).iloc[0].to_dict()

        return {
            "display_name": city["display_name"],
            "metrics": {
                "baseline_lst_c": float(metrics['baseline_lst_c']),
                "hotspot_share_pct": float(metrics['hotspot_share_pct']),
                "mean_ndvi": float(metrics['mean_ndvi'])
            },
            "scenarios": scenarios_dict,
            "best_scenario": best_scenario,
            "map_html": map_html
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
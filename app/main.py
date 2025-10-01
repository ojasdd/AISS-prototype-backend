# app/main.py
import asyncio
from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select
from app.database import init_db, get_session
from app.models import Faculty, Classroom, Course, Timeslot, Timetable
from app import scheduler
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import json 
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="SIH Timetable Prototype")

origins = [
    "https://aiss-prototype.vercel.app",  # your frontend
    "http://localhost:5173",              # local dev if needed
]
# Add CORS middleware - MUST be before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],   # or restrict: ["GET", "POST"]
    allow_headers=["*"],
)

app.mount("/exports", StaticFiles(directory="exports"), name="exports")

# Prevent concurrent scheduler runs
_generate_lock = asyncio.Lock()

@app.on_event("startup")
def on_startup():
    init_db()

# --- Create endpoints ---
@app.post("/faculty", response_model=Faculty)
def create_faculty(f: Faculty, session: Session = Depends(get_session)):
    session.add(f)
    session.commit()
    session.refresh(f)
    return f

@app.post("/classroom", response_model=Classroom)
def create_classroom(r: Classroom, session: Session = Depends(get_session)):
    session.add(r)
    session.commit()
    session.refresh(r)
    return r

@app.post("/course", response_model=Course)
def create_course(c: Course, session: Session = Depends(get_session)):
    session.add(c)
    session.commit()
    session.refresh(c)
    return c

@app.post("/timeslot", response_model=Timeslot)
def create_timeslot(t: Timeslot, session: Session = Depends(get_session)):
    session.add(t)
    session.commit()
    session.refresh(t)
    return t

# Fetch generated timetable (joined info)
@app.get("/timetable")
def get_timetable(session: Session = Depends(get_session)):
    rows = session.exec(select(Timetable)).all()
    return rows

class Dataset(BaseModel):
    faculties: List[Dict]
    courses: List[Dict]
    classrooms: List[Dict]
    timeslots: List[Dict]

@app.post("/upload-dataset")
def upload_dataset(data: Dataset):
    try:
        # Save the dataset into a JSON file
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(data.dict(), f, indent=4)
        
        return {"message": "Dataset saved to data.json", "size": len(data.courses)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving dataset: {str(e)}")

# Trigger timetable generation
@app.post("/timetable/generate")
async def generate_timetable_endpoint():
    try:
        from app.scheduler import generate_timetable
        
        # Use lock to prevent concurrent generation
        async with _generate_lock:
            success = generate_timetable(30)
            
        if success:
            return {"status": "success", "message": "Timetable generated successfully!"}
        else:
            raise HTTPException(
                status_code=400, 
                detail="Failed to generate timetable. Check if data.json exists and contains valid data."
            )
    except Exception as e:
        print(f"Error in generate_timetable_endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error generating timetable: {str(e)}"
        )
import json
import pandas as pd
from pathlib import Path
from ortools.sat.python import cp_model
from typing import Dict, Tuple
from sqlmodel import Session, select
from app.database import engine
from app.models import Timetable
from sqlalchemy.orm import Session  # Import from sqlalchemy
from sqlalchemy import delete       # Import delete function

OUTPUT_DIR = Path("exports")
OUTPUT_DIR.mkdir(exist_ok=True)

DATA_FILE = Path("data.json")  # Path to the JSON file


def _clear_timetable():
    """
    Clear the timetable export files and database entries.
    """
    # Remove timetable export files
    if (OUTPUT_DIR / "timetable.json").exists():
        (OUTPUT_DIR / "timetable.json").unlink()
    if (OUTPUT_DIR / "timetable.xlsx").exists():
        (OUTPUT_DIR / "timetable.xlsx").unlink()
    
    # Clear database
    with Session(engine) as session:
        stmt = delete(Timetable)  # Create a delete statement
        session.execute(stmt)     # Execute the delete statement
        session.commit()          # Commit the transaction

def _normalize_data(data: dict) -> dict:
    """
    Transform frontend data format to solver format.
    Converts string IDs to integers and adds missing fields.
    """
    # Create ID mappings
    faculty_id_map = {f["id"]: idx + 1 for idx, f in enumerate(data.get("faculties", []))}
    course_id_map = {c["id"]: idx + 1 for idx, c in enumerate(data.get("courses", []))}
    classroom_id_map = {r["id"]: idx + 1 for idx, r in enumerate(data.get("classrooms", []))}
    timeslot_id_map = {t["id"]: idx + 1 for idx, t in enumerate(data.get("timeslots", []))}
    
    # Transform faculties
    faculties = []
    for f in data.get("faculties", []):
        faculties.append({
            "id": faculty_id_map[f["id"]],
            "name": f["name"],
            "original_id": f["id"]
        })
    
    # Transform courses
    courses = []
    for c in data.get("courses", []):
        courses.append({
            "id": course_id_map[c["id"]],
            "name": c["name"],
            "sessions_per_week": c.get("requiredSlots", 1),
            "size": c.get("size", 30),  # Default to 30 students if not provided
            "faculty_id": faculty_id_map.get(c.get("faculty_id"), 1),  # Default to first faculty
            "original_id": c["id"]
        })
    
    # Transform classrooms
    classrooms = []
    for r in data.get("classrooms", []):
        classrooms.append({
            "id": classroom_id_map[r["id"]],
            "name": r["name"],
            "capacity": r.get("capacity", 50),
            "type": r.get("type", "Lecture"),
            "original_id": r["id"]
        })
    
    # Transform timeslots
    timeslots = []
    for t in data.get("timeslots", []):
        timeslots.append({
            "id": timeslot_id_map[t["id"]],
            "label": t["label"],
            "original_id": t["id"]
        })
    
    return {
        "faculties": faculties,
        "courses": courses,
        "classrooms": classrooms,
        "timeslots": timeslots,
        "id_mappings": {
            "faculty": faculty_id_map,
            "course": course_id_map,
            "classroom": classroom_id_map,
            "timeslot": timeslot_id_map
        }
    }

def generate_timetable(time_limit_seconds: int = 30) -> bool:
    """
    Build and solve a CP-SAT model.
    Saves results to timetable.json, timetable.xlsx, and database.
    """
    # Load data from data.json
    if not DATA_FILE.exists():
        print("Data file not found!")
        return False

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    # Normalize data for solver
    data = _normalize_data(raw_data)
    courses = data["courses"]
    timeslots = data["timeslots"]
    classrooms = data["classrooms"]
    faculties = data["faculties"]

    if not (courses and timeslots and classrooms):
        print("Insufficient data to generate timetable!")
        return False

    # Build model
    model = cp_model.CpModel()
    assign: Dict[Tuple[int, int, int], cp_model.IntVar] = {}

    for c in courses:
        for t in timeslots:
            for r in classrooms:
                if r["capacity"] >= c["size"]:
                    name = f"x_c{c['id']}_t{t['id']}_r{r['id']}"
                    assign[(c["id"], t["id"], r["id"])] = model.NewBoolVar(name)

    # Constraints
    # Constraint 1: Each course must have exact number of sessions per week
    for c in courses:
        vars_for_course = [v for (cid, _, _), v in assign.items() if cid == c["id"]]
        if not vars_for_course:
            print(f"No valid timeslots for course {c['name']}")
            return False
        model.Add(sum(vars_for_course) == c["sessions_per_week"])

    # Constraint 2: No room can have multiple classes at same time
    for t in timeslots:
        for r in classrooms:
            vars_here = [v for (cid, tid, rid), v in assign.items()
                         if tid == t["id"] and rid == r["id"]]
            if vars_here:
                model.Add(sum(vars_here) <= 1)

    # Constraint 3: No faculty can teach multiple classes at same time
    course_to_fac = {c["id"]: c["faculty_id"] for c in courses}
    faculty_ids = [f["id"] for f in faculties]
    for f_id in faculty_ids:
        for t in timeslots:
            vars_here = [v for (cid, tid, _), v in assign.items()
                         if tid == t["id"] and course_to_fac.get(cid) == f_id]
            if vars_here:
                model.Add(sum(vars_here) <= 1)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        _clear_timetable()

        # Collect rows for JSON/Excel/Database
        timetable_records = []
        db_entries = []

        for (cid, tid, rid), var in assign.items():
            if solver.Value(var) == 1:
                course = next(c for c in courses if c["id"] == cid)
                faculty = next(f for f in faculties if f["id"] == course["faculty_id"])
                classroom = next(r for r in classrooms if r["id"] == rid)
                timeslot = next(t for t in timeslots if t["id"] == tid)

                # Add to export records
                timetable_records.append({
                    "course": course["name"],
                    "faculty": faculty["name"],
                    "classroom": classroom["name"],
                    "timeslot": timeslot["label"]
                })
                
                # Prepare database entry
                db_entries.append({
                    "course_id": cid,
                    "faculty_id": course["faculty_id"],  # Include faculty_id here
                    "timeslot_id": tid,
                    "classroom_id": rid
                })

        # Save to database
        with Session(engine) as session:
            for entry in db_entries:
                timetable_entry = Timetable(**entry)
                session.add(timetable_entry)
            session.commit()

        # Save JSON
        with open(OUTPUT_DIR / "timetable.json", "w", encoding="utf-8") as f:
            json.dump(timetable_records, f, indent=4)

        # Save Excel
        df = pd.DataFrame(timetable_records)
        df.to_excel(OUTPUT_DIR / "timetable.xlsx", index=False)

        print(f"Timetable generated successfully! {len(timetable_records)} entries created.")
        return True
    else:
        print("No feasible solution found!")
        return False
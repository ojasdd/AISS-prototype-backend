# app/models.py
from sqlmodel import SQLModel, Field
from typing import Optional

class Faculty(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    department: Optional[str] = None
    max_hours_per_day: Optional[int] = 8

class Classroom(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    capacity: int
    features: Optional[str] = None  # csv/json string for simplicity

class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str
    name: str
    faculty_id: Optional[int] = Field(default=None, foreign_key="faculty.id")
    size: int
    sessions_per_week: int = 3
    duration_slots: int = 1   # number of contiguous timeslots per session

class Timeslot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    day_of_week: int  # 0=Mon .. 6=Sun
    slot_index: int   # e.g., 0..n-1 for daily slots
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class Timetable(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id")
    faculty_id: int = Field(foreign_key="faculty.id")
    classroom_id: int = Field(foreign_key="classroom.id")
    timeslot_id: int = Field(foreign_key="timeslot.id")

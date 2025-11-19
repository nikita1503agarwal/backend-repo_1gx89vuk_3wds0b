"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Class name lowercased = collection name
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional

class User(BaseModel):
    name: str = Field(..., description="Full name of the contributor")
    email: Optional[str] = Field(None, description="Email address")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")

class Link(BaseModel):
    title: str = Field(..., description="Display title for the tool or resource")
    url: HttpUrl = Field(..., description="The link URL")
    labels: List[str] = Field(default_factory=list, description="Tags like CSS, SVG, Backend")
    added_by: str = Field(..., description="Identifier for who added the link (name or email)")
    description: Optional[str] = Field(None, description="Optional short description")
    clicks: int = Field(0, ge=0, description="Total number of clicks")

class LinkCreate(BaseModel):
    title: str
    url: HttpUrl
    labels: List[str] = []
    added_by: str
    description: Optional[str] = None

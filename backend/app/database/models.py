from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, JSON, Boolean, false
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    notebooks = relationship("Notebook", back_populates="owner", cascade="all, delete-orphan")

class Notebook(Base):
    __tablename__ = "notebooks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="notebooks")
    documents = relationship("Document", back_populates="notebook", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="notebook", cascade="all, delete-orphan")
    presentations = relationship("Presentation", back_populates="notebook", cascade="all, delete-orphan")


class DocumentStatus:
    """Lifecycle of a document. Task 3 only uses UPLOADED; the AI ingestion
    pipeline (future task) moves it through the other states."""
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    notebook_id = Column(Integer, ForeignKey("notebooks.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # --- Task 3: document management metadata ---
    # (filename = display name, file_path = path relative to the uploads dir)
    file_size = Column(Integer, nullable=False, default=0)        # bytes
    mime_type = Column(String, nullable=True)
    sha256 = Column(String, index=True, nullable=True)            # duplicate detection
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="UPLOADED")   # ingestion lifecycle
    error = Column(Text, nullable=True)                           # ingestion error (future)

    notebook = relationship("Notebook", back_populates="documents")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    notebook_id = Column(Integer, ForeignKey("notebooks.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    notebook = relationship("Notebook", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    sender = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")

class PresentationStatus:
    """Lifecycle of a generated presentation (docs/presentation-jobs.md)."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"      # JOB-04
    CANCELLED = "CANCELLED"        # JOB-04
    INTERRUPTED = "INTERRUPTED"    # JOB-05

 
class Presentation(Base):
    __tablename__ = "presentations"
    id = Column(Integer, primary_key=True, index=True)
    notebook_id = Column(Integer, ForeignKey("notebooks.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default=PresentationStatus.PENDING)
    stage = Column(String, nullable=True)  # queued / outline / content 3/8 / rendering / done
    options = Column(JSON, nullable=False)  # what the user asked for
    deck = Column(JSON, nullable=True)  # Task 2's deck JSON (PresentationContent)
    file_path = Column(String, nullable=True)  # relative to data/artifacts
    error = Column(Text, nullable=True)
    outline = Column(JSON, nullable=True)
    context = Column(JSON, nullable=True)
    progress = Column(JSON, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False, server_default=false())
    slide_versions = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
 
    notebook = relationship("Notebook", back_populates="presentations")

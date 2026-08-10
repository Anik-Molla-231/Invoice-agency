"""
Database Configuration - Complete file with all models
"""

from sqlalchemy import create_engine, text, Column, Integer, String, Float, Boolean, DateTime, JSON, LargeBinary, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
from typing import Generator
import os

# ==========================================
# DATABASE URL
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///invoices.db")

# ==========================================
# ENGINE CONFIGURATION
# ==========================================

# is_sqlite = DATABASE_URL.startswith("sqlite")

# connect_args = {}
# if is_sqlite:
#     connect_args = {"check_same_thread": False}

is_sqlite = False
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "sslmode": "require",
        "connect_timeout": 10,
        "keepalives_idle": 5,
        "keepalives_interval": 2,
        "keepalives_count": 2,
    },
    pool_pre_ping=True,           # ✅ Check connection before using
    pool_recycle=300,              # ✅ Recycle connections every 5 minutes
    pool_size=5,                   # ✅ Max connections in pool
    max_overflow=10,               # ✅ Extra connections if needed
)

# ==========================================
# SESSION MAKER
# ==========================================
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# ==========================================
# DEPENDENCY
# ==========================================
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# MODELS - ALL IN ONE PLACE
# ==========================================

class InvoiceDB(Base):
    """Invoice model - stores all invoice data"""
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, index=True)

    client_id = Column(String, ForeignKey("clients.client_id"), index=True)
    
    # Basic info
    invoice_number = Column(String, index=True, nullable=True)
    vendor_name = Column(String, index=True, nullable=True)
    vendor_email = Column(String, nullable=True)
    invoice_date = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    
    # Financials
    subtotal = Column(Float, default=0)
    tax = Column(Float, default=0)
    total = Column(Float, index=True)
    currency = Column(String, default="USD")
    
    # Line items (JSON)
    line_items = Column(JSON, default=list)
    
    # Classification
    category = Column(String, nullable=True)
    account_code = Column(String, nullable=True)
    classification_confidence = Column(String, default="low")
    classification_method = Column(String, default="unknown")
    
    # Status
    status = Column(String, default="received")  # received, extracted, categorised, pending_approval, approved, rejected, synced, paid
    confidence_score = Column(Integer, default=100)
    warnings = Column(JSON, default=list)
    
    # File
    file_name = Column(String, nullable=True)
    file_hash = Column(String, unique=True, index=True, nullable=True)
    file_content = Column(LargeBinary, nullable=True)
    raw_text = Column(String, nullable=True)
    source = Column(String, nullable=True)  # email, upload, api
    
    # Approval
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_sent_at = Column(DateTime, nullable=True)
    approval_channel = Column(String, nullable=True)  # slack, email
    
    # Sync
    synced_to = Column(String, nullable=True)  # quickbooks, xero, netsuite
    synced_id = Column(String, nullable=True)
    synced_at = Column(DateTime, nullable=True)
    
    # Payment reminders
    payment_status = Column(String, default="pending")  # pending, paid, overdue
    last_reminder_sent = Column(DateTime, nullable=True)
    reminder_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ClientDB(Base):
    """Client model - stores client configurations"""
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, unique=True, index=True)
    client_name = Column(String, index=True)
    contact_email = Column(String)
    contact_phone = Column(String, nullable=True)
    billing_email = Column(String, nullable=True)

    api_key = Column(String, unique=True, index=True, nullable=True)
    
    tier = Column(String, default="starter")  # starter, professional, enterprise, white_label
    status = Column(String, default="trial")  # active, trial, paused, suspended, cancelled
    
    config = Column(JSON, default=dict)
    approver_email = Column(String, nullable=True)
    approver_slack_channel = Column(String, nullable=True)
    auto_approve_threshold = Column(Float, default=1000.0)
    
    accounting_platform = Column(String, default="quickbooks")
    accounting_credentials = Column(JSON, nullable=True)
    white_label_config = Column(JSON, nullable=True)
    
    subscription_id = Column(String, nullable=True)
    billing_cycle = Column(String, default="monthly")
    next_billing_date = Column(DateTime, nullable=True)
    
    monthly_invoice_limit = Column(Integer, default=100)
    current_month_invoices = Column(Integer, default=0)
    last_reset_date = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    chart_of_accounts = Column(JSON, default=dict)

# ==========================================
# INIT DATABASE
# ==========================================
def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")
    """Initialize database and test connections."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("✅ Database connected successfully!")
    except Exception as e:
        print(f"⚠️ Database connection issue: {e}")

def cleanup_session(db: Session):
    """Clean up a database session."""
    try:
        db.close()
    except Exception:
        pass

# ==========================================
# TEST
# ==========================================
if __name__ == "__main__":
    print(f"📊 Database URL: {DATABASE_URL}")
    print(f"📁 Type: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    
    try:
        with engine.connect() as conn:
            if is_sqlite:
                result = conn.execute("SELECT sqlite_version()")
            else:
                pass
            #     result = conn.execute("SELECT version()")
            # version = result.fetchone()[0]
            # print(f"✅ Connected successfully! Version: {version}")
        
        init_db()
        
        if is_sqlite:
            db_path = DATABASE_URL.replace("sqlite:///", "")
            print(f"📁 Database file: {db_path}")
            if os.path.exists(db_path):
                size = os.path.getsize(db_path) / 1024
                print(f"📏 File size: {size:.2f} KB")
        
        print("✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
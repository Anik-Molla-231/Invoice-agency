# create_db.py
"""
Create database tables for the Invoice Agency (PostgreSQL)
"""

import os
import sys
from pathlib import Path
from sqlalchemy import text

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import init_db, engine, Base
from core.database import InvoiceDB, ClientDB


def create_database():
    """Create all tables in PostgreSQL."""
    
    print("📊 Creating database tables...")
    print(f"🔗 Connected to: {os.getenv('DATABASE_URL', 'postgresql://...')}")
    
    try:
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Connected to: {version[:30]}...")
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        print("✅ Database tables created successfully!")
        
        # List tables
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if tables:
            print("\n📋 Tables created:")
            for table_name in tables:
                print(f"  - {table_name}")
        else:
            print("⚠️ No tables found. Check your models.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure PostgreSQL is running and your .env file has:")
        print("DATABASE_URL=postgresql://username:password@localhost:5432/database_name")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check if DATABASE_URL is set
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL not found in .env file!")
        print("   Add: DATABASE_URL=postgresql://username:password@localhost:5432/invoice_agency")
        sys.exit(1)
    
    create_database()
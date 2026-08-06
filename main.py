from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import schedule
import time
import threading
from typing import Dict
from contextlib import asynccontextmanager
from sqlalchemy import func, extract
import secrets
import os
import shutil

from core.database import init_db
from agents.intake_agent import IntakeAgent
from agents.extractor_agent import ExtractorAgent
from agents.categoriser_agent import CategoriserAgent
from agents.approval_agent import ApprovalAgent
from agents.sync_agent import SyncAgent
from agents.reminder_agent import ReminderAgent
from core.config import config
if not config.openai_api_key:
    print("⚠️ WARNING: OPENAI_API_KEY not set. Extractor agent will not work.")
    extractor_agent = None
else:
    extractor_agent = ExtractorAgent()
from core.database import SessionLocal, InvoiceDB, ClientDB

# ------------------- Application Lifespan -------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    # Startup
    try:
        config.validate()
    except ValueError as e:
        print(f"❌ Configuration Error:\n{str(e)}")
        raise
    
    init_db()
    print("🚀 Invoice Automation Agency Started")
    print("=" * 60)
    print(f"📧 Monitoring: {config.email_user}")
    print(f"🤖 Auto-approve threshold: ${config.auto_approve_threshold:.2f}")
    print(f"📊 Accounting platform: {sync_agent.platform}")
    print("=" * 60)
    
    # Start scheduler in background
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    yield  # Application is running
    
    # Shutdown
    print("🛑 Invoice Automation Agency Shutting Down")

app = FastAPI(title="Invoice Automation Agency", version="1.0", lifespan=lifespan)

# ------------------- CORS Middleware -------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agents
intake_agent = IntakeAgent()
extractor_agent = ExtractorAgent()
categoriser_agent = CategoriserAgent(client_id="default")
approval_agent = ApprovalAgent()
sync_agent = SyncAgent(platform=config.accounting_platform)
reminder_agent = ReminderAgent()

# ------------------- API Key Authentication -------------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_current_client(
    request: Request,
    api_key: str = Depends(api_key_header)
) -> ClientDB:
    """
    FastAPI Dependency.
    Authenticates the client using API Key and loads their config.
    This runs on every request.
    """
    
    # Option 1: Check header
    if not api_key:
        # Option 2: Check query parameter (for testing)
        api_key = request.query_params.get("api_key")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API Key. Provide via X-API-Key header or ?api_key= parameter"
        )
    
    # Query database
    db = SessionLocal()
    client = db.query(ClientDB).filter(ClientDB.api_key == api_key).first()
    db.close()
    
    if not client:
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key"
        )
    
    # Check if client is active
    if client.status not in ["active", "trial"]:
        raise HTTPException(
            status_code=403,
            detail=f"Account {client.status}. Please contact support."
        )
    
    # Store client in request state for other parts of the app
    request.state.client = client
    request.state.client_config = client.config or {}
    
    return client

# ------------------- API Endpoints -------------------

@app.get("/")
async def root():
    return {
        "message": "Invoice Automation Agency API",
        "endpoints": {
            "/docs": "API Documentation",
            "/api/invoices": "List all invoices",
            "/api/upload-invoice": "Upload a new invoice",
            "/api/spend-summary": "Spend analytics"
        }
    }

@app.post("/api/process-all")
async def process_all():
    """Manually trigger the entire pipeline."""
    results = {}
    
    # Step 1: Intake
    intake_results = intake_agent.process_inbox()
    results["intake"] = intake_results
    
    # Step 2: Extract
    extract_results = extractor_agent.process_pending()
    results["extract"] = extract_results
    
    # Step 3: Categorise
    categorise_results = categoriser_agent.process_extracted()
    results["categorise"] = categorise_results
    
    # Step 4: Send Approvals
    approve_results = approval_agent.process_categorised(config.notification_email)
    results["approve"] = approve_results
    
    # Step 5: Sync (if auto-approve enabled)
    # sync_results = sync_agent.process_approved()
    # results["sync"] = sync_results
    
    return JSONResponse(results)

@app.get("/api/invoices")
async def get_invoices(
    client: ClientDB = Depends(get_current_client),
    status: str = None
):
    """Get all invoices for the authenticated client with optional status filter."""
    db = SessionLocal()
    try:
        query = db.query(InvoiceDB).filter(
            InvoiceDB.client_id == client.client_id
        )
        
        if status:
            query = query.filter(InvoiceDB.status == status)
        
        invoices = query.order_by(InvoiceDB.created_at.desc()).all()
        
        return [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "vendor": inv.vendor_name,
                "total": inv.total,
                "status": inv.status,
                "category": inv.category,
                "created_at": inv.created_at
            }
            for inv in invoices
        ]
    finally:
        db.close()

@app.get("/api/invoices/{invoice_id}")
async def get_invoice_detail(
    invoice_id: int,
    client: ClientDB = Depends(get_current_client)
):
    """Get detailed invoice information for the authenticated client."""
    db = SessionLocal()
    try:
        invoice = db.query(InvoiceDB).filter(
            InvoiceDB.id == invoice_id,
            InvoiceDB.client_id == client.client_id
        ).first()
        
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "vendor_name": invoice.vendor_name,
            "vendor_email": invoice.vendor_email,
            "invoice_date": invoice.invoice_date,
            "due_date": invoice.due_date,
            "subtotal": invoice.subtotal,
            "tax": invoice.tax,
            "total": invoice.total,
            "currency": invoice.currency,
            "line_items": invoice.line_items,
            "category": invoice.category,
            "account_code": invoice.account_code,
            "status": invoice.status,
            "confidence_score": invoice.confidence_score,
            "warnings": invoice.warnings,
            "approved_by": invoice.approved_by,
            "approved_at": invoice.approved_at,
            "synced_to": invoice.synced_to,
            "synced_id": invoice.synced_id,
            "payment_status": invoice.payment_status,
            "created_at": invoice.created_at
        }
    finally:
        db.close()

@app.post("/api/upload-invoice")
async def upload_invoice(
    file: UploadFile = File(...),
    client: ClientDB = Depends(get_current_client)
):
    """Upload and process a new invoice for the authenticated client."""
    
    # Save uploaded file temporarily
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # Parse the invoice using extractor agent
        with open(temp_path, "rb") as f:
            pdf_content = f.read()
        
        extracted = extractor_agent.parse(pdf_content)
        
        # Save to database with client_id
        db = SessionLocal()
        invoice = InvoiceDB(
            client_id=client.client_id,
            invoice_number=extracted.invoice_number,
            vendor_name=extracted.vendor_name,
            vendor_email=extracted.vendor_email,
            total=extracted.total,
            line_items=[item.dict() for item in extracted.line_items],
            status="extracted",
            file_name=file.filename,
            confidence_score=extracted.confidence_score,
            warnings=extracted.warnings,
            created_at=datetime.utcnow()
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        db.close()
        
        # Cleanup
        os.remove(temp_path)
        
        return {
            "status": "success",
            "invoice_id": invoice.id,
            "client": client.client_name,
            "invoice_number": invoice.invoice_number,
            "total": invoice.total
        }
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.post("/api/invoices/{invoice_id}/approve")
async def manually_approve(
    invoice_id: int,
    approved_by: str = "api",
    client: ClientDB = Depends(get_current_client)
):
    """Manually approve an invoice for the authenticated client."""
    db = SessionLocal()
    try:
        invoice = db.query(InvoiceDB).filter(
            InvoiceDB.id == invoice_id,
            InvoiceDB.client_id == client.client_id
        ).first()
        
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        if invoice.status != "pending_approval":
            raise HTTPException(status_code=400, detail=f"Invoice is already {invoice.status}")
        
        invoice.status = "approved"
        invoice.approved_by = approved_by
        invoice.approved_at = datetime.utcnow()
        db.commit()
        
        return {"status": "approved", "invoice_id": invoice_id}
    finally:
        db.close()

@app.post("/api/invoices/{invoice_id}/reject")
async def manually_reject(
    invoice_id: int,
    reason: str = "Manual rejection",
    client: ClientDB = Depends(get_current_client)
):
    """Manually reject an invoice for the authenticated client."""
    db = SessionLocal()
    try:
        invoice = db.query(InvoiceDB).filter(
            InvoiceDB.id == invoice_id,
            InvoiceDB.client_id == client.client_id
        ).first()
        
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        if invoice.status != "pending_approval":
            raise HTTPException(status_code=400, detail=f"Invoice is already {invoice.status}")
        
        invoice.status = "rejected"
        current_warnings = invoice.warnings if invoice.warnings is not None else []
        if not isinstance(current_warnings, list):
            current_warnings = []
        invoice.warnings = current_warnings + [f"Rejected: {reason}"]
        db.commit()
        
        return {"status": "rejected", "invoice_id": invoice_id}
    finally:
        db.close()

@app.get("/api/spend-yearly")
async def get_yearly_spending(client: ClientDB = Depends(get_current_client)):
    """Get yearly spending breakdown for the authenticated client."""
    db = SessionLocal()
    
    try:
        results = db.query(
            extract('year', InvoiceDB.created_at).label('year'),
            func.sum(InvoiceDB.total).label('total_spent'),
            func.count(InvoiceDB.id).label('invoice_count')
        ).filter(
            InvoiceDB.client_id == client.client_id,
            InvoiceDB.status.in_(["approved", "synced", "paid"]),
            InvoiceDB.total.isnot(None)
        ).group_by(
            extract('year', InvoiceDB.created_at)
        ).order_by(
            extract('year', InvoiceDB.created_at).desc()
        ).all()
        
        yearly_data = []
        for row in results:
            yearly_data.append({
                "year": int(row.year),
                "total_spent": float(row.total_spent) if row.total_spent else 0,
                "invoice_count": row.invoice_count
            })
        
        db.close()
        return {"success": True, "data": yearly_data}
        
    except Exception as e:
        db.close()
        return {"success": False, "error": str(e)}

@app.get("/api/spend-monthly/{year}")
async def get_monthly_spending(
    year: int,
    client: ClientDB = Depends(get_current_client)
):
    """Get monthly spending breakdown for a specific year for the authenticated client."""
    db = SessionLocal()
    
    try:
        results = db.query(
            extract('month', InvoiceDB.created_at).label('month'),
            func.sum(InvoiceDB.total).label('total_spent'),
            func.count(InvoiceDB.id).label('invoice_count')
        ).filter(
            InvoiceDB.client_id == client.client_id,
            InvoiceDB.status.in_(["approved", "synced", "paid"]),
            InvoiceDB.total.isnot(None),
            extract('year', InvoiceDB.created_at) == year
        ).group_by(
            extract('month', InvoiceDB.created_at)
        ).order_by(
            extract('month', InvoiceDB.created_at)
        ).all()
        
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        monthly_data = []
        for month_num in range(1, 13):
            month_name = months[month_num - 1]
            found = False
            for row in results:
                if row.month == month_num:
                    monthly_data.append({
                        "month": month_name,
                        "month_num": month_num,
                        "total_spent": float(row.total_spent) if row.total_spent else 0,
                        "invoice_count": row.invoice_count
                    })
                    found = True
                    break
            if not found:
                monthly_data.append({
                    "month": month_name,
                    "month_num": month_num,
                    "total_spent": 0,
                    "invoice_count": 0
                })
        
        db.close()
        return {"success": True, "year": year, "data": monthly_data}
        
    except Exception as e:
        db.close()
        return {"success": False, "error": str(e)}

@app.get("/api/spend-summary")
async def get_spend_summary(client: ClientDB = Depends(get_current_client)):
    """Get spend analytics for the authenticated client."""
    db = SessionLocal()
    try:
        # Total spent
        total_spent = db.query(func.sum(InvoiceDB.total)).filter(
            InvoiceDB.client_id == client.client_id,
            InvoiceDB.status.in_(["approved", "synced", "paid"])
        ).scalar() or 0
        
        # Total invoices
        total_invoices = db.query(func.count(InvoiceDB.id)).filter(
            InvoiceDB.client_id == client.client_id,
            InvoiceDB.status.in_(["approved", "synced", "paid"])
        ).scalar() or 0
        
        # Vendor breakdown
        vendor_spend = db.query(
            InvoiceDB.vendor_name,
            func.sum(InvoiceDB.total).label("total_spent"),
            func.count(InvoiceDB.id).label("invoice_count")
        ).filter(
            InvoiceDB.client_id == client.client_id,
            InvoiceDB.status.in_(["approved", "synced", "paid"])
        ).group_by(InvoiceDB.vendor_name).all()
        
        return {
            "total_spent": float(total_spent),
            "total_invoices": total_invoices,
            "vendor_breakdown": [
                {
                    "vendor": v.vendor_name or "Unknown",
                    "total": float(v.total_spent),
                    "percentage": (float(v.total_spent) / float(total_spent) * 100) if total_spent > 0 else 0,
                    "invoice_count": v.invoice_count
                }
                for v in vendor_spend
            ]
        }
    finally:
        db.close()


@app.get("/api/clients/me/branding")
async def get_client_branding(client: ClientDB = Depends(get_current_client)):
    """Get client's company name and logo."""
    config = client.config or {}
    return {
        "company_name": config.get("company_name", client.client_name),
        "logo_base64": config.get("logo_base64")
    }

# ------------------- Scheduled Jobs -------------------

def run_intake_job():
    try:
        print(f"[{datetime.now()}] Running invoice intake...")
        intake_agent.process_inbox()
    except Exception as e:
        print(f"[ERROR] Intake job failed: {str(e)}")

def run_extraction_job():
    try:
        print(f"[{datetime.now()}] Running extraction...")
        extractor_agent.process_pending()
    except Exception as e:
        print(f"[ERROR] Extraction job failed: {str(e)}")

def run_categorisation_job():
    try:
        print(f"[{datetime.now()}] Running categorisation...")
        categoriser_agent.process_extracted()
    except Exception as e:
        print(f"[ERROR] Categorisation job failed: {str(e)}")

def run_approval_job():
    try:
        print(f"[{datetime.now()}] Sending approvals...")
        approval_agent.process_categorised(config.notification_email)
    except Exception as e:
        print(f"[ERROR] Approval job failed: {str(e)}")

def run_sync_job():
    try:
        print(f"[{datetime.now()}] Syncing to accounting...")
        sync_agent.process_approved()
    except Exception as e:
        print(f"[ERROR] Sync job failed: {str(e)}")

def run_reminder_job():
    try:
        print(f"[{datetime.now()}] Sending payment reminders...")
        reminder_agent.process_overdue()
    except Exception as e:
        print(f"[ERROR] Reminder job failed: {str(e)}")

def run_scheduler():
    """Run all scheduled jobs with error handling."""
    # Every 15 minutes: check email
    schedule.every(15).minutes.do(run_intake_job)
    
    # Every 30 minutes: process pending invoices
    schedule.every(30).minutes.do(run_extraction_job)
    schedule.every(30).minutes.do(run_categorisation_job)
    
    # Every hour: send approvals
    schedule.every(1).hours.do(run_approval_job)
    
    # Every 6 hours: sync to accounting
    schedule.every(6).hours.do(run_sync_job)
    
    # Every day at 9 AM: send payment reminders
    schedule.every().day.at("09:00").do(run_reminder_job)
    
    print(f"[{datetime.now()}] Scheduler initialized with {len(schedule.jobs)} jobs")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            print(f"[ERROR] Scheduler error: {str(e)}")
            time.sleep(60)

# main.py - Add this at the very bottom
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
from fastapi import FastAPI, Request, HTTPException
import json
import hmac
import hashlib
from core.database import SessionLocal, InvoiceDB
from datetime import datetime
import os

app = FastAPI(title="Slack Webhook Handler")

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")

def verify_slack_request(request_body: bytes, signature: str, timestamp: str) -> bool:
    """Verify that the request is from Slack."""
    if not SLACK_SIGNING_SECRET:
        return True  # Skip verification in dev
    
    basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}".encode('utf-8')
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode('utf-8'),
        basestring,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)

@app.post("/slack/interactions")
async def handle_slack_interactions(request: Request):
    """Handle Slack interactive button clicks."""
    
    # Verify request
    signature = request.headers.get("X-Slack-Signature", "")
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    request_body = await request.body()
    
    if not verify_slack_request(request_body, signature, timestamp):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
    
    # Parse payload
    form_data = await request.form()
    payload = json.loads(form_data.get("payload", "{}"))
    
    # Extract data
    action = payload.get("actions", [{}])[0]
    action_id = action.get("action_id")
    value = action.get("value")
    user = payload.get("user", {}).get("name", "unknown")
    
    if action_id == "approve_invoice":
        invoice_id = int(value.split("_")[1])
        return await approve_invoice(invoice_id, user)
    
    elif action_id == "reject_invoice":
        invoice_id = int(value.split("_")[1])
        return await reject_invoice(invoice_id, user)
    
    elif action_id == "view_invoice":
        invoice_id = int(value.split("_")[1])
        return await view_invoice(invoice_id)
    
    return {"status": "ok"}

async def approve_invoice(invoice_id: int, user: str):
    """Approve an invoice from Slack."""
    db = SessionLocal()
    invoice = db.query(InvoiceDB).filter(InvoiceDB.id == invoice_id).first()
    
    if not invoice:
        db.close()
        return {"status": "error", "message": "Invoice not found"}
    
    if invoice.status != "pending_approval":
        db.close()
        return {"status": "error", "message": f"Invoice is already {invoice.status}"}
    
    invoice.status = "approved"
    invoice.approved_by = f"slack_{user}"
    invoice.approved_at = datetime.utcnow()
    db.commit()
    db.close()
    
    return {
        "status": "success",
        "message": f"Invoice #{invoice.invoice_number} approved by {user}"
    }

async def reject_invoice(invoice_id: int, user: str):
    """Reject an invoice from Slack."""
    db = SessionLocal()
    invoice = db.query(InvoiceDB).filter(InvoiceDB.id == invoice_id).first()
    
    if not invoice:
        db.close()
        return {"status": "error", "message": "Invoice not found"}
    
    if invoice.status != "pending_approval":
        db.close()
        return {"status": "error", "message": f"Invoice is already {invoice.status}"}
    
    invoice.status = "rejected"
    invoice.approved_by = f"slack_{user}"
    invoice.approved_at = datetime.utcnow()
    current_warnings = invoice.warnings if invoice.warnings is not None else []
    if not isinstance(current_warnings, list):
        current_warnings = []
    invoice.warnings = current_warnings + [f"Rejected by {user}"]
    db.commit()
    db.close()
    
    return {
        "status": "success",
        "message": f"Invoice #{invoice.invoice_number} rejected by {user}"
    }

async def view_invoice(invoice_id: int):
    """Return invoice details for Slack."""
    db = SessionLocal()
    invoice = db.query(InvoiceDB).filter(InvoiceDB.id == invoice_id).first()
    db.close()
    
    if not invoice:
        return {"status": "error", "message": "Invoice not found"}
    
    return {
        "status": "success",
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "vendor": invoice.vendor_name,
            "total": invoice.total,
            "date": invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else None,
            "status": invoice.status,
            "line_items": invoice.line_items
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
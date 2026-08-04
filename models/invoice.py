from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

class InvoiceStatus(str, Enum):
    RECEIVED = "received"
    EXTRACTED = "extracted"
    CATEGORISED = "categorised"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SYNCED = "synced"
    PAID = "paid"

class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float
    account_code: Optional[str] = None  # Chart of accounts mapping

class Invoice(BaseModel):
    # Basic fields
    invoice_number: str
    vendor_name: str
    vendor_email: Optional[str] = None
    date: datetime
    due_date: Optional[datetime] = None
    
    # Financials
    line_items: List[LineItem]
    subtotal: float
    tax: float
    total: float
    currency: str = "USD"
    
    # Classification
    category: Optional[str] = None  # e.g., "Marketing", "Software", "Consulting"
    account_code: Optional[str] = None  # Chart of accounts code
    
    # Metadata
    source: str  # email, upload, etc.
    file_url: Optional[str] = None
    raw_text: Optional[str] = None
    
    # Status
    status: InvoiceStatus = InvoiceStatus.RECEIVED
    confidence_score: int = 100
    warnings: List[str] = []
    
    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    
    # Sync
    synced_to: Optional[str] = None  # "quickbooks", "xero", "netsuite"
    synced_id: Optional[str] = None  # External system ID
    synced_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
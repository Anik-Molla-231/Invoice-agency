from typing import Dict, List, Optional
from datetime import datetime
import json
import requests
from core.config import config
from core.database import SessionLocal, InvoiceDB

class SyncAgent:
    """Syncs approved invoices to QuickBooks, Xero, or NetSuite."""
    
    def __init__(self, platform: str = "quickbooks"):
        self.platform = platform
        self.platform_config = self._load_platform_config()
    
    def _load_platform_config(self) -> Dict:
        """Load platform-specific configuration."""
        if self.platform == "quickbooks":
            return {
                "client_id": config.quickbooks_client_id,
                "client_secret": config.quickbooks_client_secret,
                "refresh_token": config.quickbooks_refresh_token,
                "realm_id": config.quickbooks_realm_id,
                "base_url": "https://quickbooks.api.intuit.com/v3/company"
            }
        elif self.platform == "xero":
            return {
                "client_id": config.xero_client_id,
                "client_secret": config.xero_client_secret,
                "refresh_token": config.xero_refresh_token,
                "tenant_id": config.xero_tenant_id,
                "base_url": "https://api.xero.com/api.xro/2.0"
            }
        else:
            raise ValueError(f"Platform {self.platform} not supported")
    
    def _get_quickbooks_access_token(self) -> str:
        """Refresh QuickBooks access token using OAuth2."""
        if not self.platform_config.get("refresh_token"):
            raise ValueError("QuickBooks refresh_token not configured")
        
        try:
            response = requests.post(
                "https://oauth.platform.intuit.com/oauth2/tokens/bearer",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.platform_config["refresh_token"]
                },
                auth=(self.platform_config["client_id"], self.platform_config["client_secret"])
            )
            response.raise_for_status()
            token_data = response.json()
            return token_data.get("access_token")
        except Exception as e:
            raise RuntimeError(f"Failed to refresh QuickBooks access token: {str(e)}")
    
    def _get_xero_access_token(self) -> str:
        """Refresh Xero access token using OAuth2."""
        if not self.platform_config.get("refresh_token"):
            raise ValueError("Xero refresh_token not configured")
        
        try:
            response = requests.post(
                "https://identity.xero.com/connect/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.platform_config["refresh_token"],
                    "client_id": self.platform_config["client_id"],
                    "client_secret": self.platform_config["client_secret"]
                }
            )
            response.raise_for_status()
            token_data = response.json()
            return token_data.get("access_token")
        except Exception as e:
            raise RuntimeError(f"Failed to refresh Xero access token: {str(e)}")
    
    def sync_to_quickbooks(self, invoice_data: Dict) -> Dict:
        """Sync invoice to QuickBooks as a Bill."""
        try:
            access_token = self._get_quickbooks_access_token()
            realm_id = self.platform_config["realm_id"]
            base_url = self.platform_config["base_url"]
            
            # QuickBooks Bill payload
            qb_payload = {
                "VendorRef": {
                    "name": invoice_data.get("vendor_name", "Unknown Vendor")
                },
                "DocNumber": invoice_data.get("invoice_number", ""),
                "TxnDate": invoice_data.get("invoice_date", datetime.now().strftime("%Y-%m-%d")),
                "DueDate": invoice_data.get("due_date", ""),
                "Line": [
                    {
                        "Amount": item.get("total", 0),
                        "Description": item.get("description", ""),
                        "DetailType": "AccountBasedExpenseLineDetail",
                        "AccountBasedExpenseLineDetail": {
                            "AccountRef": {
                                "name": invoice_data.get("category", "Other Expenses")
                            },
                            "BillableStatus": "NotBillable"
                        }
                    }
                    for item in invoice_data.get("line_items", [])
                ],
                "TotalAmt": invoice_data.get("total", 0)
            }
            
            url = f"{base_url}/{realm_id}/bill?minorversion=65"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = requests.post(url, json=qb_payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            return {
                "success": True,
                "sync_id": result.get("Bill", {}).get("Id"),
                "sync_date": datetime.now().isoformat(),
                "platform": "quickbooks"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "platform": "quickbooks"
            }
    
    def sync_to_xero(self, invoice_data: Dict) -> Dict:
        """Sync invoice to Xero as a Bill."""
        try:
            access_token = self._get_xero_access_token()
            tenant_id = self.platform_config["tenant_id"]
            base_url = self.platform_config["base_url"]
            
            # Xero Bill payload
            xero_payload = {
                "Type": "ACCREC",
                "Contact": {
                    "Name": invoice_data.get("vendor_name", "Unknown Vendor")
                },
                "Date": invoice_data.get("invoice_date", datetime.now().strftime("%Y-%m-%d")),
                "DueDate": invoice_data.get("due_date", ""),
                "InvoiceNumber": invoice_data.get("invoice_number", ""),
                "LineItems": [
                    {
                        "Description": item.get("description", ""),
                        "Quantity": item.get("quantity", 1),
                        "UnitAmount": item.get("unit_price", 0),
                        "AccountCode": invoice_data.get("account_code", "5900"),
                        "TaxType": "NONE"
                    }
                    for item in invoice_data.get("line_items", [])
                ],
                "Total": invoice_data.get("total", 0)
            }
            
            url = f"{base_url}/Invoices"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Xero-Tenant-Id": tenant_id,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = requests.post(url, json=xero_payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            return {
                "success": True,
                "sync_id": result.get("Invoices", [{}])[0].get("InvoiceID"),
                "sync_date": datetime.now().isoformat(),
                "platform": "xero"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "platform": "xero"
            }
    
    def process_approved(self) -> List[dict]:
        """
        Process all invoices with status 'approved'.
        Sync to accounting software.
        """
        db = SessionLocal()
        invoices = db.query(InvoiceDB).filter(
            InvoiceDB.status == "approved",
            InvoiceDB.synced_to.is_(None)  # Not yet synced
        ).all()
        
        processed = []
        
        for invoice in invoices:
            invoice_dict = {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "vendor_name": invoice.vendor_name,
                "total": invoice.total,
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else None,
                "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
                "category": invoice.category,
                "account_code": invoice.account_code,
                "line_items": invoice.line_items or []
            }
            
            # Sync to platform
            if self.platform == "quickbooks":
                result = self.sync_to_quickbooks(invoice_dict)
            elif self.platform == "xero":
                result = self.sync_to_xero(invoice_dict)
            else:
                result = {"success": False, "error": f"Unknown platform: {self.platform}"}
            
            # Update database
            if result["success"]:
                invoice.status = "synced"
                invoice.synced_to = self.platform
                invoice.synced_id = result.get("sync_id")
                invoice.synced_at = datetime.utcnow()
            else:
                current_warnings = invoice.warnings if invoice.warnings is not None else []
                if not isinstance(current_warnings, list):
                    current_warnings = []
                invoice.warnings = current_warnings + [f"Sync failed: {result.get('error', 'Unknown error')}"]
            
            db.commit()
            
            processed.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "success": result.get("success", False),
                "sync_id": result.get("sync_id"),
                "error": result.get("error")
            })
        
        db.close()
        return processed

if __name__ == "__main__":
    agent = SyncAgent(platform="quickbooks")
    results = agent.process_approved()
    print(f"✅ Synced {len(results)} invoices to QuickBooks")
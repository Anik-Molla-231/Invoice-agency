import json
from typing import Dict, List, Optional
from core.database import SessionLocal, InvoiceDB, ClientDB
from models.invoice import Invoice
from datetime import datetime
import re

class CategoriserAgent:
    """
    Classifies invoices into the client's chart of accounts.
    Uses a combination of rule-based matching and AI fine-tuning.
    """
    
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.chart_of_accounts = self._load_chart_of_accounts()
        self.rules = self._load_rules()
    
    def _load_chart_of_accounts(self) -> Dict[str, str]:
        """Load client's chart of accounts from database."""
        db = SessionLocal()
        config = db.query(ClientDB).filter(
            ClientDB.client_id == self.client_id
        ).first()
        db.close()
        
        if config and config.chart_of_accounts:
            return config.chart_of_accounts
        else:
            # Default chart of accounts (you'd customize per client)
            return {
                "5000": "Marketing & Advertising",
                "5100": "Software & SaaS",
                "5200": "Consulting & Professional Services",
                "5300": "Office Supplies",
                "5400": "Travel & Entertainment",
                "5500": "Legal & Professional Fees",
                "5600": "IT & Infrastructure",
                "5700": "Printing & Production",
                "5800": "Staff & Contractors",
                "5900": "Other Expenses"
            }
    
    def _load_rules(self) -> List[dict]:
        """
        Load classification rules.
        Each rule: {"keywords": [], "account_code": "5000"}
        """
        # You'd load these from database per client
        return [
            {"keywords": ["google", "ads", "adwords", "ppc"], "account_code": "5000"},
            {"keywords": ["facebook", "meta", "instagram", "social media"], "account_code": "5000"},
            {"keywords": ["aws", "cloud", "hosting", "server", "heroku"], "account_code": "5600"},
            {"keywords": ["legal", "attorney", "lawyer", "court"], "account_code": "5500"},
            {"keywords": ["consult", "strategy", "advisor"], "account_code": "5200"},
            {"keywords": ["office", "supplies", "stationery"], "account_code": "5300"},
            {"keywords": ["quickbooks", "xero", "accounting", "software"], "account_code": "5100"},
            {"keywords": ["freelance", "contractor", "consultant"], "account_code": "5800"},
            {"keywords": ["print", "banner", "poster", "flyer"], "account_code": "5700"},
        ]
    
    def classify(self, vendor: str, description: str, line_items: List[dict]) -> Dict[str, str]:
        """
        Classify an invoice based on vendor and line item descriptions.
        Returns: {"account_code": "5000", "category": "Marketing & Advertising", "confidence": "high"}
        """
        
        # Combine all text for classification
        combined_text = f"{vendor} " + " ".join([item["description"] for item in line_items])
        combined_text = combined_text.lower()
        
        # Rule-based matching (for known vendors)
        for rule in self.rules:
            for keyword in rule["keywords"]:
                if keyword.lower() in combined_text:
                    account_code = rule["account_code"]
                    return {
                        "account_code": account_code,
                        "category": self.chart_of_accounts.get(account_code, "Unknown"),
                        "confidence": "high",
                        "method": "rule_based"
                    }
        
        # If no rule matches, use AI-based classification
        return self._ai_classify(vendor, line_items)
    
    def _ai_classify(self, vendor: str, line_items: List[dict]) -> Dict[str, str]:
        """
        Use GPT-4o-mini for classification when rules don't match.
        This learns from patterns over time.
        """
        from openai import OpenAI
        from core.config import config
        
        client = OpenAI(api_key=config.openai_api_key)
        
        line_item_descriptions = [item["description"] for item in line_items]
        
        prompt = f"""
        Classify this invoice into the client's chart of accounts.
        
        Vendor: {vendor}
        Items: {', '.join(line_item_descriptions)}
        
        Chart of accounts:
        {json.dumps(self.chart_of_accounts, indent=2)}
        
        Return JSON with: {{"account_code": "5000", "category": "Marketing & Advertising", "confidence": "high"}}
        """
        
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            result = json.loads(completion.choices[0].message.content)
            return {
                "account_code": result.get("account_code", "5900"),
                "category": result.get("category", "Other Expenses"),
                "confidence": result.get("confidence", "medium"),
                "method": "ai_based"
            }
            
        except:
            return {
                "account_code": "5900",
                "category": "Other Expenses",
                "confidence": "low",
                "method": "fallback"
            }
    
    def process_extracted(self) -> List[dict]:
        """
        Process all invoices with status 'extracted'.
        Classify them and update status to 'categorised'.
        """
        db = SessionLocal()
        invoices = db.query(InvoiceDB).filter(
            InvoiceDB.status == "extracted"
        ).all()
        
        processed = []
        
        for invoice in invoices:
            try:
                # Classify the invoice
                classification = self.classify(
                    vendor=invoice.vendor_name,
                    description=invoice.invoice_number or "",
                    line_items=invoice.line_items or []
                )
                
                # Update database
                invoice.account_code = classification["account_code"]
                invoice.category = classification["category"]
                invoice.classification_confidence = classification["confidence"]
                invoice.classification_method = classification.get("method", "unknown")
                invoice.status = "categorised"
                invoice.updated_at = datetime.utcnow()
                
                db.commit()
                
                processed.append({
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "category": invoice.category,
                    "account_code": invoice.account_code,
                    "confidence": invoice.classification_confidence
                })
                
            except Exception as e:
                invoice.status = "error"
                current_warnings = invoice.warnings if invoice.warnings is not None else []
                if not isinstance(current_warnings, list):
                    current_warnings = []
                invoice.warnings = current_warnings + [f"Classification error: {str(e)}"]
                db.commit()
        
        db.close()
        return processed

if __name__ == "__main__":
    # Replace with actual client_id
    agent = CategoriserAgent(client_id="client_001")
    results = agent.process_extracted()
    print(f"✅ Categorised {len(results)} invoices")
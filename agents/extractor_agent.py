# agents/extractor_agent.py - With OCR Support

import sys
from pathlib import Path


import os
import requests
import re
import io
import json
import pdfplumber
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from core.config import config
from core.database import SessionLocal, InvoiceDB

# ==========================================
# OCR IMPORTS (Optional - only if installed)
# ==========================================
try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
    print("✅ OCR support enabled")
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️ OCR not installed. Scanned PDFs will fail.")

# ==========================================
# PYDANTIC MODELS
# ==========================================

class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

class ExtractedInvoice(BaseModel):
    invoice_number: str = "UNKNOWN"
    vendor_name: str = "UNKNOWN"
    vendor_email: Optional[str] = None
    date: str = datetime.now().strftime("%Y-%m-%d")
    due_date: Optional[str] = None
    line_items: List[LineItem] = []
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    currency: str = "USD"
    confidence_score: int = 50
    warnings: List[str] = []

# ==========================================
# EXTRACTOR AGENT
# ==========================================

class ExtractorAgent:
    def __init__(self):
        self.api_key = config.openai_api_key
        if not self.api_key:
            print("⚠️ WARNING: OPENAI_API_KEY not set in .env")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    # def __init__(self, model: str = "llama3.2"):
    #     self.model = model
    #     self.ollama_url = "http://localhost:11434/api/generate"  
    #     print(f"🤖 Using Ollama model: {model}")
    
    def extract_text(self, pdf_content: bytes) -> str:
        """
        Extract text from PDF.
        - First tries pdfplumber (for text-based PDFs)
        - If that fails, tries OCR (for scanned PDFs)
        """
        # Try pdfplumber first (text-based PDFs)
        try:
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                text = "".join([p.extract_text() or "" for p in pdf.pages])
                if text.strip():
                    print(f"   ✅ Extracted {len(text)} chars using pdfplumber")
                    return text[:10000]
        except Exception as e:
            print(f"   ⚠️ pdfplumber failed: {e}")
        
        # Fallback to OCR (if available)
        if OCR_AVAILABLE:
            try:
                print("   🔍 Trying OCR...")
                images = convert_from_bytes(pdf_content, dpi=200)
                text = ""
                for img in images:
                    text += pytesseract.image_to_string(img) + "\n"
                if text.strip():
                    print(f"   ✅ Extracted {len(text)} chars using OCR")
                    return text[:10000]
            except Exception as e:
                print(f"   ⚠️ OCR failed: {e}")
        
        print("   ❌ No text extracted from PDF")
        return ""
    
    def parse(self, pdf_content: bytes) -> ExtractedInvoice:
        """Parse invoice using GPT-4o-mini."""
        
        raw_text = self.extract_text(pdf_content)
        
        if not raw_text:
            print("   ❌ No text extracted")
            return ExtractedInvoice(
                warnings=["Could not extract text from PDF"]
            )
        
        if not self.client:
            print("   ❌ OpenAI client not configured")
            return ExtractedInvoice(
                warnings=["OpenAI API key missing"]
            )
        
        # ==========================================
        # IMPROVED PROMPT - Handles messy formats
        # ==========================================
        prompt = f"""
        You are an expert invoice parser. Extract data from this invoice text.
        
        RULES:
        1. Find the invoice number, vendor name, date, and total amount
        2. Look for line items (description, quantity, unit price, total)
        3. If the text is messy (like "Logo1$500$500"), parse as: Item="Logo", Qty=1, Price=500, Total=500
        4. If a field is missing, use null
        5. Return valid JSON only
        
        INVOICE TEXT:
        {raw_text}
        
        Return JSON with:
        {{
            "invoice_number": "string or null",
            "vendor_name": "string or null",
            "date": "YYYY-MM-DD or null",
            "total": number,
            "line_items": [
                {{"description": "string", "quantity": number, "unit_price": number, "total": number}}
            ]
        }}
        """
        
        try:
            completion = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract data from invoices. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            result = json.loads(completion.choices[0].message.content)
            
            # Parse line items
            line_items = []
            for item in result.get("line_items", []):
                try:
                    line_items.append(LineItem(
                        description=str(item.get("description", "Unknown")),
                        quantity=float(item.get("quantity", 1)),
                        unit_price=float(item.get("unit_price", 0)),
                        total=float(item.get("total", 0))
                    ))
                except:
                    pass
            
            return ExtractedInvoice(
                invoice_number=result.get("invoice_number", "UNKNOWN"),
                vendor_name=result.get("vendor_name", "UNKNOWN"),
                date=result.get("date", datetime.now().strftime("%Y-%m-%d")),
                total=float(result.get("total", 0)),
                line_items=line_items,
                confidence_score=80
            )
            
        except Exception as e:
            print(f"   ❌ Parsing failed: {e}")
            return ExtractedInvoice(
                warnings=[f"Parsing error: {str(e)}"]
            )


    # def parse(self, pdf_content: bytes) -> ExtractedInvoice:
    #     """Parse invoice using Ollama with robust JSON extraction."""
        
        
    #     raw_text = self.extract_text(pdf_content)
        
    #     if not raw_text:
    #         print("   ❌ No text extracted")
    #         return ExtractedInvoice(
    #             warnings=["Could not extract text from PDF"]
    #         )
        
    #     # ==========================================
    #     # UPDATED PROMPT - Explicitly forbid extra text
    #     # ==========================================
    #     prompt = f"""
    #     You are an expert invoice parser. Extract data from this invoice text.

    #     RULES:
    #     1. Find the invoice number, vendor name, date, and total amount
    #     2. Look for line items (description, quantity, unit price, total)
    #     3. If a field is missing, use null
    #     4. **CRITICAL: Return ONLY valid JSON. No explanation, no markdown, no comments.**

    #     INVOICE TEXT:
    #     {raw_text}

    #     Return JSON with:
    #     {{
    #         "invoice_number": "string or null",
    #         "vendor_name": "string or null",
    #         "date": "YYYY-MM-DD or null",
    #         "total": number,
    #         "line_items": [
    #             {{"description": "string", "quantity": number, "unit_price": number, "total": number}}
    #         ]
    #     }}
    #     """
            
    #     try:
    #             response = requests.post(
    #                 self.ollama_url,
    #                 json={
    #                     "model": self.model,
    #                     "prompt": prompt,
    #                     "stream": False,
    #                     "temperature": 0.0,
    #                     "format": "json"  # <-- NEW: Forces Ollama to output JSON
    #                 },
    #                 timeout=120
    #             )
                
    #             if response.status_code != 200:
    #                 print(f"   ❌ Ollama error: {response.status_code}")
    #                 return ExtractedInvoice(
    #                     warnings=[f"Ollama API error: {response.status_code}"]
    #                 )
                
    #             result_text = response.json().get("response", "")
    #             # ==========================================
    #             # IMPROVED JSON EXTRACTION
    #             # ==========================================
                
    #             # Remove markdown code blocks
    #             result_text = re.sub(r'```json\s*', '', result_text)
    #             result_text = re.sub(r'```\s*', '', result_text)
                
    #             # Find JSON object (stricter pattern)
    #             json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
    #             if not json_match:
    #                 # Try falling back to finding any JSON object
    #                 json_match = re.search(r'\{[^{}]*"invoice_no"[^{}]*\}', result_text, re.DOTALL)
    #                 if not json_match:
    #                     print(f"   ❌ No JSON found in response")
    #                     print(f"   Response preview: {result_text[:200]}...")
    #                     return ExtractedInvoice(
    #                         warnings=["Ollama response didn't contain valid JSON"]
    #                     )

                
                
    #             # Clean the matched JSON string
    #             json_str = json_match.group()
                
    #             # Remove any trailing commas (common LLM mistake)
    #             json_str = re.sub(r',\s*}', '}', json_str)
    #             json_str = re.sub(r',\s*]', ']', json_str)
                                
    #             # Parse JSON
    #             try:
    #                 result = json.loads(json_str)
    #             except json.JSONDecodeError as e:
    #                 print(f"   ❌ JSON decode error: {e}")
    #                 print(f"   Raw JSON: {json_match.group()[:200]}...")
    #                 return ExtractedInvoice(
    #                     warnings=[f"Invalid JSON: {str(e)}"]
    #                 )
                
    #             # Parse line items
    #             line_items = []
    #             for item in result.get("line_items", []):
    #                 try:
    #                     line_items.append(LineItem(
    #                         description=str(item.get("description", "Unknown")),
    #                         quantity=float(item.get("quantity", 1)),
    #                         unit_price=float(item.get("unit_price", 0)),
    #                         total=float(item.get("total", 0))
    #                     ))
    #                 except:
    #                     pass
                            
    #                 return ExtractedInvoice(
    #                     invoice_number=result.get("invoice_number", "UNKNOWN"),
    #                     vendor_name=result.get("vendor_name", "UNKNOWN"),
    #                     date=result.get("date", datetime.now().strftime("%Y-%m-%d")),
    #                     total=float(result.get("total", 0)),
    #                     line_items=line_items,
    #                     confidence_score=80
    #                 )
                    
    #     except json.JSONDecodeError as e:
    #         print(f"   ❌ JSON parse error: {e}")
    #         print(f"   Response preview: {result_text[:200]}...")
    #         return ExtractedInvoice(
    #             warnings=[f"JSON parsing error: {str(e)}"]
    #         )
    #     except requests.exceptions.ConnectionError:
    #         print("   ❌ Cannot connect to Ollama. Run: ollama serve")
    #         return ExtractedInvoice(
    #             warnings=["Ollama not running. Start with: ollama serve"]
    #         )
    #     except Exception as e:
    #         print(f"   ❌ Parsing failed: {e}")
    #         return ExtractedInvoice(
    #             warnings=[f"Parsing error: {str(e)}"]
    #         )
    
    def process_pending(self) -> List[dict]:
        """Process all invoices with status 'received'."""
        db = SessionLocal()
        invoices = db.query(InvoiceDB).filter(
            InvoiceDB.status == "received"
        ).all()
        
        print(f"📄 Found {len(invoices)} pending invoices")
        
        processed = []
        
        for invoice in invoices:
            print(f"\n  Processing invoice #{invoice.id}...")
            
            if not invoice.file_content:
                print(f"    ⚠️ No file content")
                invoice.status = "error"
                invoice.warnings = ["No file content"]
                db.commit()
                continue
            
            try:
                extracted = self.parse(invoice.file_content)
                
                invoice.invoice_number = extracted.invoice_number
                invoice.vendor_name = extracted.vendor_name
                invoice.total = extracted.total
                invoice.line_items = [item.dict() for item in extracted.line_items]
                invoice.status = "extracted"
                invoice.confidence_score = extracted.confidence_score
                invoice.warnings = extracted.warnings
                invoice.updated_at = datetime.utcnow()
                
                db.commit()
                
                processed.append({
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "vendor": invoice.vendor_name,
                    "total": invoice.total
                })
                
                print(f"    ✅ Extracted: {invoice.invoice_number} - ${invoice.total}")
                
            except Exception as e:
                print(f"    ❌ Error: {e}")
                invoice.status = "error"
                invoice.warnings = [f"Extraction error: {str(e)}"]
                db.commit()
        
        db.close()
        return processed


if __name__ == "__main__":
    agent = ExtractorAgent()
    results = agent.process_pending()
    print(f"\n✅ Extracted {len(results)} invoices")
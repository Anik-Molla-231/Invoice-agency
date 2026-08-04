import imaplib
import email
from email.header import decode_header
import os
import base64
from typing import List, Tuple
from datetime import datetime
import hashlib
from sqlalchemy.exc import IntegrityError
from core.config import config
from core.database import SessionLocal, InvoiceDB

class IntakeAgent:
    """Monitors email inbox and extracts invoice attachments."""
    
    def __init__(self):
        self.host = config.email_host
        self.user = config.email_user
        self.password = config.email_password
        self.folder = config.email_inbox_folder
        self.mail = None  # Initialize connection tracker
    
    def connect(self):
        """Connect to IMAP server."""
        try:
            self.mail = imaplib.IMAP4_SSL(self.host)
            self.mail.login(self.user, self.password)
            self.mail.select(self.folder)
            print(f"✅ Connected to IMAP server {self.host} and selected folder {self.folder}")
        except Exception as e:
            self.mail = None
            raise RuntimeError(f"Failed to connect to IMAP server: {str(e)}")
    
    def search_unprocessed(self) -> List[Tuple[str, bytes]]:
        """
        Search for emails with invoice attachments that haven't been processed.
        Returns: [(email_id, raw_email_bytes)]
        """
        # Search for unread emails or emails with specific subject
        status, messages = self.mail.search(None, 'UNSEEN')
        
        if status != 'OK':
            return []
        
        email_ids = messages[0].split()
        results = []
        
        for eid in email_ids:
            status, msg_data = self.mail.fetch(eid, '(RFC822)')
            if status != 'OK':
                continue
            
            raw_email = msg_data[0][1]
            results.append((eid.decode(), raw_email))
        
        return results
    
    def extract_attachments(self, raw_email: bytes) -> List[Tuple[str, bytes]]:
        """
        Extract PDF attachments from email.
        Returns: [(filename, file_content)]
        """
        msg = email.message_from_bytes(raw_email)
        attachments = []
        
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            
            filename = part.get_filename()
            if filename:
                # Decode filename if encoded
                filename = decode_header(filename)[0][0]
                if isinstance(filename, bytes):
                    filename = filename.decode('utf-8')
                
                # Only process PDFs
                if filename.lower().endswith('.pdf'):
                    payload = part.get_payload(decode=True)
                    attachments.append((filename, payload))
        
        return attachments
    
    def process_inbox(self) -> List[dict]:
        """
        Main loop: Check email, download attachments, save to database.
        Returns: List of processed invoices.
        """
        self.connect()
        processed = []
        
        try:
            emails = self.search_unprocessed()
            
            for email_id, raw_email in emails:
                attachments = self.extract_attachments(raw_email)
                
                for filename, content in attachments:
                    # Create unique hash for deduplication
                    file_hash = hashlib.md5(content).hexdigest()
                    
                    # Check if already processed
                    db = SessionLocal()
                    try:
                        existing = db.query(InvoiceDB).filter(
                            InvoiceDB.file_hash == file_hash
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Save to database with status "received"
                        invoice = InvoiceDB(
                            file_name=filename,
                            file_hash=file_hash,
                            file_content=content,  # Stored as blob (or save to S3)
                            status="received",
                            source=f"email_{email_id}"
                        )
                        db.add(invoice)
                        try:
                            db.commit()
                            db.refresh(invoice)
                            
                            processed.append({
                                "invoice_id": invoice.id,
                                "file_name": filename,
                                "status": "received"
                            })
                        except IntegrityError:
                            db.rollback()
                            # File already exists (race condition or reprocessing)
                            # Skip silently or log for debugging
                            print(f"[INFO] File {filename} already processed (skipping duplicate)")
                    finally:
                        db.close()
            
            return processed
        finally:
            # Safely close IMAP connection if it was established
            if self.mail is not None:
                try:
                    self.mail.close()
                    self.mail.logout()
                except Exception:
                    pass  # Connection might already be closed or in invalid state

# For scheduled execution
if __name__ == "__main__":
    agent = IntakeAgent()
    results = agent.process_inbox()
    print(f"✅ Processed {len(results)} new invoices from inbox")
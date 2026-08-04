from typing import List, Dict
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from core.config import config
from core.database import SessionLocal, InvoiceDB

class ReminderAgent:
    """
    Monitors overdue accounts receivable and sends payment reminders.
    Escalates if no response in 3 days.
    """
    
    def __init__(self):
        self.email_from = config.email_user
        self.email_password = config.email_password
        self.reminder_days = config.payment_reminder_days
        self.escalation_days = 3  # Escalate after 3 days of no reply
    
    def get_overdue_invoices(self) -> List[Dict]:
        """
        Get all invoices that are overdue and not yet marked as paid.
        """
        db = SessionLocal()
        
        today = datetime.now().date()
        
        # Invoices with due_date < today and status = 'synced' (already synced to accounting)
        invoices = db.query(InvoiceDB).filter(
            InvoiceDB.due_date.isnot(None),
            InvoiceDB.due_date < today,
            InvoiceDB.status == "synced",
            InvoiceDB.payment_status.in_(['pending', 'overdue'])
        ).all()
        
        # Also include invoices from accounting system (if synced)
        # You'd have a separate table for AR invoices
        
        db.close()
        
        return [{
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "vendor_name": inv.vendor_name,
            "vendor_email": inv.vendor_email,
            "total": inv.total,
            "due_date": inv.due_date,
            "days_overdue": (today - inv.due_date).days,
            "last_reminder_sent": inv.last_reminder_sent,
            "reminder_count": inv.reminder_count or 0,
            "payment_status": inv.payment_status or "pending"
        } for inv in invoices]
    
    def send_reminder(self, invoice: Dict, reminder_type: str) -> bool:
        """
        Send a payment reminder email.
        reminder_type: "first", "second", "third", "escalation"
        """
        
        if invoice.get("vendor_email") is None:
            return False
        
        # Customize message based on reminder type
        templates = {
            "first": {
                "subject": f"Reminder: Invoice #{invoice.get('invoice_number')} is Due",
                "body": f"""
                Dear {invoice.get('vendor_name')},
                
                This is a friendly reminder that invoice #{invoice.get('invoice_number')} for ${invoice.get('total', 0):.2f} is now {invoice.get('days_overdue')} days overdue.
                
                Please make payment at your earliest convenience.
                
                Invoice Details:
                - Amount: ${invoice.get('total', 0):.2f}
                - Due Date: {invoice.get('due_date').strftime('%Y-%m-%d')}
                - Days Overdue: {invoice.get('days_overdue')}
                
                If you have already made payment, please ignore this message.
                """
            },
            "second": {
                "subject": f"⚠️ URGENT: Invoice #{invoice.get('invoice_number')} is Overdue",
                "body": f"""
                Dear {invoice.get('vendor_name')},
                
                Invoice #{invoice.get('invoice_number')} for ${invoice.get('total', 0):.2f} is now {invoice.get('days_overdue')} days overdue.
                
                We kindly request immediate payment to avoid any disruption in service.
                
                If you have any questions about this invoice, please contact our accounts team.
                """
            },
            "third": {
                "subject": f"🚨 FINAL NOTICE: Invoice #{invoice.get('invoice_number')} Overdue",
                "body": f"""
                Dear {invoice.get('vendor_name')},
                
                This is a FINAL NOTICE. Invoice #{invoice.get('invoice_number')} for ${invoice.get('total', 0):.2f} is now {invoice.get('days_overdue')} days overdue.
                
                Payment must be received within 48 hours, or we may need to escalate this matter.
                
                Please make payment immediately.
                """
            },
            "escalation": {
                "subject": f"🔴 ESCALATED: Invoice #{invoice.get('invoice_number')} - Action Required",
                "body": f"""
                Dear {invoice.get('vendor_name')},
                
                This invoice #{invoice.get('invoice_number')} for ${invoice.get('total', 0):.2f} has been escalated to our management team.
                
                Please contact us IMMEDIATELY to resolve this payment issue.
                
                You can reach our accounts team at {self.email_from}.
                
                This is a formal escalation. Please treat it with urgency.
                """
            }
        }
        
        template = templates.get(reminder_type, templates["first"])
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = template["subject"]
            msg['From'] = self.email_from
            msg['To'] = invoice.get("vendor_email")
            
            # Add BCC to internal team
            msg['Bcc'] = config.notification_email
            
            html_body = template["body"].replace('\n', '<br>')
            msg.attach(MIMEText(html_body, 'html'))
            
            with smtplib.SMTP(config.email_host, 587) as server:
                server.starttls()
                server.login(self.email_from, self.email_password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"Reminder email failed: {e}")
            return False
    
    def check_for_replies(self) -> List[Dict]:
        """
        Check email inbox for replies from customers.
        Log responses and check if any action is needed.
        """
        # Implement IMAP check for specific customer replies
        # Parse reply content, update invoice status if "paid"
        pass
    
    def escalate_if_no_reply(self, invoice: Dict) -> bool:
        """
        Check if customer has not replied for escalation_days days.
        If so, send escalation email and notify team.
        """
        if invoice.get("last_reminder_sent") is None:
            return False
        
        last_sent = invoice["last_reminder_sent"]
        if (datetime.now() - last_sent).days > self.escalation_days:
            # Send escalation email
            return self.send_reminder(invoice, "escalation")
        
        return False
    
    def process_overdue(self) -> List[Dict]:
        """
        Main loop: Process all overdue invoices.
        Send reminders based on days overdue.
        """
        invoices = self.get_overdue_invoices()
        processed = []
        
        for invoice in invoices:
            days_overdue = invoice["days_overdue"]
            reminder_count = invoice.get("reminder_count", 0)
            
            # Determine reminder type
            if days_overdue <= self.reminder_days[0]:
                reminder_type = "first"
            elif days_overdue <= self.reminder_days[1]:
                reminder_type = "second"
            elif days_overdue <= self.reminder_days[2]:
                reminder_type = "third"
            else:
                reminder_type = "escalation"
            
            # Send reminder
            sent = self.send_reminder(invoice, reminder_type)
            
            if sent:
                # Update database
                db = SessionLocal()
                db_invoice = db.query(InvoiceDB).filter(InvoiceDB.id == invoice["id"]).first()
                if db_invoice:
                    db_invoice.last_reminder_sent = datetime.utcnow()
                    db_invoice.reminder_count = (db_invoice.reminder_count or 0) + 1
                    db_invoice.payment_status = "overdue"
                    db.commit()
                db.close()
                
                processed.append({
                    "invoice_id": invoice["id"],
                    "invoice_number": invoice["invoice_number"],
                    "days_overdue": days_overdue,
                    "reminder_type": reminder_type,
                    "sent": sent
                })
            
            # Check if escalation is needed (no reply for 3+ days)
            if reminder_type == "escalation":
                self.escalate_if_no_reply(invoice)
        
        return processed

if __name__ == "__main__":
    agent = ReminderAgent()
    results = agent.process_overdue()
    print(f"📧 Sent {len(results)} payment reminders")
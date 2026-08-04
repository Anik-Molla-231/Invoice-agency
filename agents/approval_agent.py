import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List
from datetime import datetime
from core.config import config
from core.database import SessionLocal, InvoiceDB

class ApprovalAgent:
    """
    Sends approval requests via Slack and Email.
    Handles one-click approval/rejection.
    """
    
    def __init__(self):
        self.slack_webhook = config.slack_webhook_url
        self.slack_channel = config.slack_channel
        self.email_from = config.email_user
        self.email_password = config.email_password
    
    def send_slack_approval(self, invoice_data: Dict) -> bool:
        """
        Send an approval request to Slack with action buttons.
        """
        if not self.slack_webhook:
            return False
        
        # Build the Slack message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📄 Invoice #{invoice_data.get('invoice_number', 'Unknown')} Pending Approval"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Vendor:*\n{invoice_data.get('vendor_name', 'Unknown')}"},
                    {"type": "mrkdwn", "text": f"*Total:*\n${invoice_data.get('total', 0):.2f}"},
                    {"type": "mrkdwn", "text": f"*Date:*\n{invoice_data.get('invoice_date', 'Unknown')}"},
                    {"type": "mrkdwn", "text": f"*Category:*\n{invoice_data.get('category', 'Uncategorised')}"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Line Items:*\n" + "\n".join([
                        f"• {item.get('description')}: {item.get('quantity')} x ${item.get('unit_price', 0):.2f} = ${item.get('total', 0):.2f}"
                        for item in invoice_data.get('line_items', [])[:5]
                    ])
                }
            },
            {
                "type": "actions",
                "block_id": "approval_actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve"},
                        "style": "primary",
                        "value": f"approve_{invoice_data.get('id')}",
                        "action_id": "approve_invoice"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "value": f"reject_{invoice_data.get('id')}",
                        "action_id": "reject_invoice"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📋 View Details"},
                        "value": f"view_{invoice_data.get('id')}",
                        "action_id": "view_invoice"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"<https://your-app.com/invoices/{invoice_data.get('id')}|View in Dashboard>"}
                ]
            }
        ]
        
        # Add warnings if confidence is low
        if invoice_data.get('warnings'):
            blocks.insert(2, {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Warnings:*\n" + "\n".join(invoice_data.get('warnings', []))
                }
            })
        
        payload = {
            "channel": self.slack_channel,
            "blocks": blocks,
            "text": f"Invoice #{invoice_data.get('invoice_number')} pending approval"  # Fallback text
        }
        
        try:
            response = requests.post(
                self.slack_webhook,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            return response.status_code == 200
        except:
            return False
    
    def send_email_approval(self, invoice_data: Dict, approver_email: str) -> bool:
        """
        Send an approval request via email.
        """
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Action Required: Invoice #{invoice_data.get('invoice_number')} Pending Approval"
            msg['From'] = self.email_from
            msg['To'] = approver_email
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px;">
                <h2>📄 Invoice #{invoice_data.get('invoice_number')} Pending Approval</h2>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td><strong>Vendor:</strong></td><td>{invoice_data.get('vendor_name', 'Unknown')}</td></tr>
                    <tr><td><strong>Total:</strong></td><td>${invoice_data.get('total', 0):.2f}</td></tr>
                    <tr><td><strong>Date:</strong></td><td>{invoice_data.get('invoice_date', 'Unknown')}</td></tr>
                    <tr><td><strong>Category:</strong></td><td>{invoice_data.get('category', 'Uncategorised')}</td></tr>
                </table>
                
                <h3>Line Items:</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #f0f0f0;">
                        <th style="padding: 8px;">Description</th>
                        <th style="padding: 8px;">Qty</th>
                        <th style="padding: 8px;">Unit Price</th>
                        <th style="padding: 8px;">Total</th>
                    </tr>
                    {''.join([
                        f"<tr><td>{item.get('description')}</td><td>{item.get('quantity')}</td><td>${item.get('unit_price', 0):.2f}</td><td>${item.get('total', 0):.2f}</td></tr>"
                        for item in invoice_data.get('line_items', [])
                    ])}
                </table>
                
                <div style="margin-top: 30px;">
                    <a href="http://127.0.0.1:8000/invoices/{invoice_data.get('id')}/approve" 
                       style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">
                        ✅ Approve
                    </a>
                    <a href="https://your-app.com/invoices/{invoice_data.get('id')}/reject" 
                       style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                        ❌ Reject
                    </a>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(config.email_host, 587) as server:
                server.starttls()
                server.login(self.email_from, self.email_password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"Email failed: {e}")
            return False
    
    def process_categorised(self, approver_email: str) -> List[dict]:
        """
        Process all invoices with status 'categorised'.
        Send approval requests via Slack and Email.
        """
        db = SessionLocal()
        
        # Auto-approve small invoices
        small_invoices = db.query(InvoiceDB).filter(
            InvoiceDB.status == "categorised",
            InvoiceDB.total <= config.auto_approve_threshold
        ).all()
        
        for invoice in small_invoices:
            invoice.status = "pending_approval"
            invoice.approval_sent_at = datetime.utcnow()
            db.commit()
            # Auto-approve silently (send notification only)
            self.send_auto_approve_notification(invoice)
        
        # Send approvals for larger invoices
        large_invoices = db.query(InvoiceDB).filter(
            InvoiceDB.status == "categorised",
            InvoiceDB.total > config.auto_approve_threshold
        ).all()
        
        processed = []
        for invoice in large_invoices:
            invoice_dict = {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "vendor_name": invoice.vendor_name,
                "total": invoice.total,
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else None,
                "category": invoice.category,
                "line_items": invoice.line_items or [],
                "warnings": invoice.warnings or []
            }
            
            # Send to Slack
            slack_sent = self.send_slack_approval(invoice_dict)
            
            # Send to Email
            email_sent = self.send_email_approval(invoice_dict, approver_email)
            
            if slack_sent or email_sent:
                invoice.status = "pending_approval"
                invoice.approval_sent_at = datetime.utcnow()
                invoice.approval_channel = "slack" if slack_sent else "email"
                db.commit()
                
                processed.append({
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "slack_sent": slack_sent,
                    "email_sent": email_sent
                })
        
        db.close()
        return processed
    
    def send_auto_approve_notification(self, invoice):
        """Send notification that invoice was auto-approved."""
    
        # Build the message
        message = f"""
            ✅ *Invoice Auto-Approved*

            *Invoice #{invoice.invoice_number}*
            • Vendor: {invoice.vendor_name}
            • Total: ${invoice.total:.2f}
            • Category: {invoice.category or 'Uncategorised'}
            • Confidence: {invoice.confidence_score}%

            *Line Items:*
            {chr(10).join([f"  • {item.get('description')}: {item.get('quantity')} x ${item.get('unit_price', 0):.2f} = ${item.get('total', 0):.2f}" for item in invoice.line_items[:5]])}

            *Reason:* Auto-approved (below ${self.auto_approve_threshold:.2f} threshold)
                """
    
        # Send to Slack (if configured)
        if self.slack_webhook:
            try:
                payload = {
                    "channel": self.slack_channel,
                    "text": f"Invoice #{invoice.invoice_number} auto-approved",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": message
                            }
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": f"<https://your-app.com/invoices/{invoice.id}|View in Dashboard>"}
                            ]
                        }
                    ]
                }
                requests.post(self.slack_webhook, json=payload)
                print(f"📨 Slack notification sent for invoice #{invoice.invoice_number}")
            except Exception as e:
                print(f"⚠️ Slack notification failed: {e}")
    
        # Send Email (if configured)
        if self.email_from and self.email_password:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = f"✅ Invoice #{invoice.invoice_number} Auto-Approved"
                msg['From'] = self.email_from
                msg['To'] = self.notification_email
                
                html = f"""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #28a745;">✅ Invoice Auto-Approved</h2>
                    <table style="border-collapse: collapse; width: 100%;">
                        <tr><td><strong>Invoice #:</strong></td><td>{invoice.invoice_number}</td></tr>
                        <tr><td><strong>Vendor:</strong></td><td>{invoice.vendor_name}</td></tr>
                        <tr><td><strong>Total:</strong></td><td>${invoice.total:.2f}</td></tr>
                        <tr><td><strong>Category:</strong></td><td>{invoice.category or 'Uncategorised'}</td></tr>
                        <tr><td><strong>Confidence:</strong></td><td>{invoice.confidence_score}%</td></tr>
                    </table>
                    <p><em>Auto-approved (below ${self.auto_approve_threshold:.2f} threshold)</em></p>
                </body>
                </html>
                """
                msg.attach(MIMEText(html, 'html'))
                
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.email_from, self.email_password)
                    server.send_message(msg)
                print(f"📧 Email notification sent for invoice #{invoice.invoice_number}")
            except Exception as e:
                print(f"⚠️ Email notification failed: {e}")

if __name__ == "__main__":
    agent = ApprovalAgent()
    # Replace with actual approver email
    results = agent.process_categorised("approver@company.com")
    print(f"✅ Sent {len(results)} approval requests")
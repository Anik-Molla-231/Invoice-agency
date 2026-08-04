import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Config:
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Model for invoice extraction
    
    # Email (Gmail/IMAP)
    email_host: str = os.getenv("EMAIL_HOST", "imap.gmail.com")
    email_user: str = os.getenv("EMAIL_USER", "")
    email_password: str = os.getenv("EMAIL_PASSWORD", "")
    email_inbox_folder: str = os.getenv("EMAIL_INBOX", "INBOX")
    notification_email: str = os.getenv("NOTIFICATION_EMAIL", "")  # Email where approval notifications are sent
    
    # Slack
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_channel: str = os.getenv("SLACK_CHANNEL", "#invoices")
    
    # QuickBooks
    quickbooks_client_id: str = os.getenv("QUICKBOOKS_CLIENT_ID", "")
    quickbooks_client_secret: str = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
    quickbooks_refresh_token: str = os.getenv("QUICKBOOKS_REFRESH_TOKEN", "")
    quickbooks_realm_id: str = os.getenv("QUICKBOOKS_REALM_ID", "")
    
    # Xero
    # xero_client_id: str = os.getenv("XERO_CLIENT_ID", "")
    # xero_client_secret: str = os.getenv("XERO_CLIENT_SECRET", "")
    # xero_refresh_token: str = os.getenv("XERO_REFRESH_TOKEN", "")
    # xero_tenant_id: str = os.getenv("XERO_TENANT_ID", "")
    
    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///invoices.db")
    
    # App Settings
    auto_approve_threshold: float = float(os.getenv("AUTO_APPROVE_THRESHOLD", "500.0"))
    accounting_platform: str = os.getenv("ACCOUNTING_PLATFORM", "quickbooks")  # quickbooks, xero, netsuite
    payment_reminder_days: list = field(default_factory=lambda: [3, 7, 14, 30])  # Days overdue to send reminders
    
    # Client-specific chart of accounts (mapped per client)
    chart_of_accounts: dict = field(default_factory=dict)  # Load from database
    
    def validate(self) -> None:
        """Validate that all required environment variables are set."""
        errors = []
        
        # Required for core functionality
        required_vars = {
            "OPENAI_API_KEY": self.openai_api_key,
            "EMAIL_USER": self.email_user,
            "EMAIL_PASSWORD": self.email_password,
            "NOTIFICATION_EMAIL": self.notification_email,
        }
        
        # Platform-specific requirements
        if self.accounting_platform == "quickbooks":
            required_vars.update({
                "QUICKBOOKS_CLIENT_ID": self.quickbooks_client_id,
                "QUICKBOOKS_CLIENT_SECRET": self.quickbooks_client_secret,
                "QUICKBOOKS_REFRESH_TOKEN": self.quickbooks_refresh_token,
                "QUICKBOOKS_REALM_ID": self.quickbooks_realm_id,
            })
        elif self.accounting_platform == "xero":
            required_vars.update({
                "XERO_CLIENT_ID": self.xero_client_id,
                "XERO_CLIENT_SECRET": self.xero_client_secret,
                "XERO_REFRESH_TOKEN": self.xero_refresh_token,
                "XERO_TENANT_ID": self.xero_tenant_id,
            })
        
        # Check for missing variables
        for var_name, var_value in required_vars.items():
            if not var_value:
                errors.append(f"Missing required environment variable: {var_name}")
        
        if errors:
            error_message = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_message)

config = Config()

# Note: Validation is called during app startup (main.py startup_event)
# to prevent the app from starting with missing required environment variables.
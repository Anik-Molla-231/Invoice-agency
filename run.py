#!/usr/bin/env python
"""
UNIVERSAL LAUNCHER - Run any agent without import errors.
Usage:
    python run.py intake
    python run.py extractor
    python run.py categoriser
    python run.py approval
    python run.py sync
    python run.py reminder
    python run.py main
    python run.py all
    python run.py process-all
"""

import sys
import os
from pathlib import Path
import core

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

# Set environment variable to indicate we're in the app
os.environ.setdefault("INVOICE_APP_ENV", "development")


def print_header(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


def run_intake():
    from agents.intake_agent import IntakeAgent
    print_header("📥 INTAKE AGENT - Checking Email")
    agent = IntakeAgent()
    results = agent.process_inbox()
    print(f"✅ Processed {len(results)} invoices from email")
    for r in results:
        print(f"  - Invoice #{r.get('invoice_id')}: {r.get('file_name')} ({r.get('status')})")


def run_extractor():
    from agents.extractor_agent import ExtractorAgent
    print_header("🤖 EXTRACTOR AGENT - Parsing Invoices")
    agent = ExtractorAgent()
    results = agent.process_pending()
    print(f"✅ Extracted data from {len(results)} invoices")
    for r in results:
        print(f"  - Invoice #{r.get('invoice_id')}: {r.get('invoice_number')} - ${r.get('total', 0):.2f}")


def run_categoriser():
    from agents.categoriser_agent import CategoriserAgent
    print_header("🏷️ CATEGORISER AGENT - Classifying Expenses")
    agent = CategoriserAgent(client_id="default")
    results = agent.process_extracted()
    print(f"✅ Categorised {len(results)} invoices")
    for r in results:
        print(f"  - Invoice #{r.get('invoice_id')}: {r.get('category')} ({r.get('account_code')})")


def run_approval():
    from agents.approval_agent import ApprovalAgent
    from core.config import config
    print_header("📧 APPROVAL AGENT - Sending Approvals")
    agent = ApprovalAgent()
    results = agent.process_categorised(config.notification_email or "admin@example.com")
    print(f"✅ Sent {len(results)} approval requests")
    for r in results:
        print(f"  - Invoice #{r.get('invoice_id')}: {r.get('invoice_number')}")


def run_sync():
    from agents.sync_agent import SyncAgent
    from core.config import config
    print_header("🔄 SYNC AGENT - Syncing to Accounting")
    platform = getattr(config, 'accounting_platform', 'quickbooks')
    agent = SyncAgent(platform=platform)
    results = agent.process_approved()
    print(f"✅ Synced {len(results)} invoices")
    for r in results:
        if r.get('success'):
            print(f"  - Invoice #{r.get('invoice_id')}: Synced to {platform}")
        else:
            print(f"  - Invoice #{r.get('invoice_id')}: Failed - {r.get('error', 'Unknown error')}")


def run_reminder():
    from agents.reminder_agent import ReminderAgent
    print_header("⏰ REMINDER AGENT - Payment Follow-ups")
    agent = ReminderAgent()
    results = agent.process_overdue()
    print(f"✅ Sent {len(results)} payment reminders")
    for r in results:
        print(f"  - Invoice #{r.get('invoice_id')}: {r.get('reminder_type')} reminder")


def run_main():
    print_header("🚀 STARTING MAIN APPLICATION")
    import uvicorn
    from main import app
    
    print("📡 Server running at http://localhost:8000")
    print("📚 API docs at http://localhost:8000/docs")
    print("📚 API docs (with prefix) at http://localhost:8000/api/docs")
    print("Press CTRL+C to stop")
    print()
    
    uvicorn.run(app, host="127.0.0.1", port=8000)


def run_process_all():
    """Call the /api/process-all endpoint via HTTP"""
    import requests
    print_header("🔄 PROCESSING ALL INVOICES")
    
    try:
        response = requests.post("http://localhost:8000/api/process-all", timeout=60)
        if response.status_code == 200:
            result = response.json()
            print("✅ Pipeline triggered successfully!")
            print(f"  - Intake: {len(result.get('intake', []))} invoices")
            print(f"  - Extract: {len(result.get('extract', []))} invoices")
            print(f"  - Categorise: {len(result.get('categorise', []))} invoices")
            print(f"  - Approve: {len(result.get('approve', []))} approvals")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
    except requests.exceptions.ConnectionError:
        print("❌ Server not running! Start with: python run.py main")
    except Exception as e:
        print(f"❌ Error: {e}")


def run_all():
    """Run all agents in sequence (except main)."""
    run_intake()
    run_extractor()
    run_categoriser()
    run_approval()
    run_sync()
    run_reminder()


def run_all_with_server():
    """Run all agents then start the server."""
    run_all()
    run_main()


def show_help():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  INVOICE AUTOMATION AGENCY - COMMANDS                       ║
╚══════════════════════════════════════════════════════════════╝

  python run.py intake        - Monitor email for invoices
  python run.py extractor     - Extract data with AI
  python run.py categoriser   - Classify expenses
  python run.py approval      - Send approval requests
  python run.py sync          - Sync to QuickBooks/Xero
  python run.py reminder      - Send payment reminders
  python run.py process-all   - Trigger full pipeline via API
  python run.py main          - Start the API server
  python run.py all           - Run all agents in sequence
  python run.py all-server    - Run all agents then start server
  python run.py help          - Show this help

Examples:
  python run.py intake
  python run.py main
  python run.py all
  python run.py process-all   # Server must be running
""")


if __name__ == "__main__":
    args = sys.argv[1:]
    
    if not args or args[0] == "help" or args[0] == "--help" or args[0] == "-h":
        show_help()
        sys.exit(0)
    
    command = args[0].lower()
    
    commands = {
        "intake": run_intake,
        "extractor": run_extractor,
        "categoriser": run_categoriser,
        "categorizer": run_categoriser,  # US spelling
        "approval": run_approval,
        "sync": run_sync,
        "reminder": run_reminder,
        "main": run_main,
        "server": run_main,
        "all": run_all,
        "all-server": run_all_with_server,
        "process-all": run_process_all,
        "process_all": run_process_all,
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"❌ Unknown command: {command}")
        print("Try: python run.py help")
        sys.exit(1)
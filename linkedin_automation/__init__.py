"""
LinkedIn Connection Automation

Autonomous, human-paced LinkedIn connection requests for prospect lists.

Usage:
    python -m linkedin_automation.cli init
    python -m linkedin_automation.cli import --csv path/to/prospects.csv --country IE
    python -m linkedin_automation.cli login
    python -m linkedin_automation.cli discover --country IE --batch-size 30
    python -m linkedin_automation.cli connect --country IE --daily-cap 30
    python -m linkedin_automation.cli dashboard

See docs/linkedin-automation-plan.md for architecture and rationale.
"""

__version__ = "0.1.0"

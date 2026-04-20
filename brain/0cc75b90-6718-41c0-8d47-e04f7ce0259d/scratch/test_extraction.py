import sys
import os

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.api.routes.resume_parse import _parse_resume, _parse_form16, _extract_bank_details

test_text = """
Name: John Doe
Email: john.doe@gmail.com
Phone: 9876543210
Experience:
Google 2020 - Present
Software Engineer
Microsoft 2018 - 2020
Junior Dev

Bank Details:
HDFC Bank
Account: 1234567890
IFSC: HDFC0001234
"""

print("--- Testing Resume Parse ---")
print(_parse_resume(test_text))

print("\n--- Testing Bank Extraction ---")
print(_extract_bank_details(test_text))

test_f16 = """
Name of Employee: John Doe
PAN: ABCDE1234F
Gross Salary: 12,00,000
Basic: 5,00,000
HRA: 2,00,000
"""
print("\n--- Testing Form-16 Parse ---")
print(_parse_form16(test_f16))

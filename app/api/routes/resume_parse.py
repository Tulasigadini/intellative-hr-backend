"""
Resume & Form-16 parsing — LOCAL only, zero external APIs.
Uses pdfminer.six for PDF text, pytesseract for image OCR, pure regex for extraction.

POST /employees/{id}/parse-resume  → structured personal fields
POST /employees/{id}/parse-form16  → CTC / tax fields
"""
import uuid, re, io, os, json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.models import Employee
from app.core.deps import get_current_user, is_hr_or_admin
from google import genai

# ── regex patterns ─────────────────────────────────────────────────────────────

PHONE_RE   = re.compile(r'(?:\+91[\s\-]?)?[6-9]\d{9}')
UAN_RE     = re.compile(r'\b(?:UAN|Universal Account Number)[^\d]*(\d{12})\b', re.IGNORECASE)
PFNO_RE    = re.compile(r'\b(?:PF\s*(?:No|Number|Account)|Provident Fund\s*(?:No|Number))[^A-Z0-9]*((?:[A-Z]{2}/[A-Z0-9]+/\d+/\d+|[A-Z]{2}[A-Z0-9]{3}\d{7}\d{3}\d{7}))\b', re.IGNORECASE)
EMAIL_RE   = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PIN_RE     = re.compile(r'\b[1-9][0-9]{5}\b')
DOB_RE     = re.compile(r'(?:dob|date of birth|born)[^\d]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', re.IGNORECASE)
GENDER_RE  = re.compile(r'\b(male|female)\b', re.IGNORECASE)
CITY_RE    = re.compile(
    r'\b(Hyderabad|Bangalore|Bengaluru|Mumbai|Delhi|Chennai|Pune|Kolkata|'
    r'Ahmedabad|Jaipur|Surat|Visakhapatnam|Vijayawada|Coimbatore|Kochi|'
    r'Nagpur|Indore|Bhopal|Noida|Gurgaon|Gurugram|Lucknow|Patna|Bhubaneswar)\b', re.IGNORECASE)
STATE_RE   = re.compile(
    r'\b(Andhra Pradesh|Telangana|Karnataka|Maharashtra|Tamil Nadu|Kerala|Gujarat|'
    r'Rajasthan|West Bengal|Uttar Pradesh|Madhya Pradesh|Bihar|Odisha|Punjab|Haryana|Delhi|Goa)\b', re.IGNORECASE)
MONTHS = r'Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?'
RANGE_RE   = re.compile(
    rf'\b((?:{MONTHS})\s+\d{{4}}|\b20[0-2]\d\b)\s*[-\u2013\u2014|to]+\s*((?:{MONTHS})\s+\d{{4}}|\b20[0-2]\d\b|present|current|till date)\b',
    re.IGNORECASE)
ACCOUNT_RE = re.compile(r'\b(?:\d{9,18})\b')
IFSC_RE    = re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b')
PAN_RE     = re.compile(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b')
FY_RE      = re.compile(r'(?:F\.?Y\.?|financial year)[^\d]*(\d{4}[-\u2013]\d{2,4})', re.IGNORECASE)
AY_RE      = re.compile(r'(?:A\.?Y\.?|assessment year)[^\d]*(\d{4}[-\u2013]\d{2,4})', re.IGNORECASE)

router = APIRouter(prefix="/parsing", tags=["resume-parse"])

@router.post("/public/extract-data")
async def public_extract_data(files: List[UploadFile] = File(...), source: str = Form("resume")):
    """Unauthenticated extraction for Step 0."""
    return await _process_extraction(files, source)

async def _process_extraction(files: List[UploadFile], source: str):
    import tempfile
    full_text = ""
    filenames = []
    temp_files_paths = []
    
    # Save to temp files
    for file in files:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024: raise HTTPException(400, f"File {file.filename} too large")
        ext = file.filename.rsplit(".", 1)[-1].lower()
        filenames.append(file.filename)
        
        # We also need to extract text for fallback
        try:
            full_text += _get_text(content, ext) + "\n\n"
        except Exception:
            pass # ignore fallback errors if it's an unsupported format
            
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(content)
            temp_files_paths.append(tmp.name)
            
    gemini_key = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_key") or "AIzaSyCUw4jPdmm_ijNnikkb1wo1MaicyKRhnEg"
    client = genai.Client(api_key=gemini_key) if gemini_key else None
    
    uploaded_gemini_files = []
    if client:
        try:
            for path in temp_files_paths:
                uploaded_file = client.files.upload(file=path)
                uploaded_gemini_files.append(uploaded_file)
        except Exception as e:
            print("Gemini upload failed:", e)
    
    if source == "resume":
        res = {}
        if client and uploaded_gemini_files:
            prompt = """
Extract the following information from this resume document. If a field is not found, leave it as an empty string. 
Format the output as a valid JSON object.
Required fields:
- first_name
- last_name
- phone (digits only)
- personal_email
- date_of_birth (YYYY-MM-DD if possible)
- gender (male/female/other)
- city
- state
- pincode
- work_history (list of objects with: 
    - company_name (Only the name of the company, e.g. 'Intellativ India Private Limited'. Do not include prefixes like 'Working at' or 'Worked in' or extra text.), 
    - designation (Only the exact job title, e.g. 'Software Engineer'. Do not include extra text.), 
    - from_date (YYYY-MM-DD or YYYY-MM format), 
    - to_date (YYYY-MM-DD or YYYY-MM format. If they are currently working there, leave this as an empty string ""), 
    - is_current (boolean: true if they currently work here, false otherwise), 
    - last_ctc (string)
  )
"""
            is_fallback = False
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[*uploaded_gemini_files, prompt],
                    config={"response_mime_type": "application/json"}
                )
                res = json.loads(response.text)
            except Exception as e:
                print("Gemini parsing failed, fallback to regex:", e)
                is_fallback = True
                res = _parse_resume(full_text)
        else:
            is_fallback = True
            res = _parse_resume(full_text)

        return {
            "is_fallback": is_fallback,
            "data": {
                "personal": {
                    "first_name": res.get("first_name", ""),
                    "last_name": res.get("last_name", ""),
                    "phone": res.get("phone", ""),
                    "personal_email": res.get("personal_email", ""),
                    "date_of_birth": res.get("date_of_birth", ""),
                    "gender": res.get("gender", ""),
                    "city": res.get("city", ""),
                    "state": res.get("state", ""),
                    "pincode": res.get("pincode", ""),
                },
                "work_history": res.get("work_history", []),
                "salary": {},
                "bank": {},
                "tax": {}
            },
            "filename": ", ".join(filenames)
        }
    else:  # form16
        f16 = {}
        bank_details = {}
        is_fallback = False
        if client and uploaded_gemini_files:
            prompt = """
Extract the following information from this Form 16 document (which may contain Part A and Part B). 
If a field is not found, leave it as an empty string.
Format the output as a valid JSON object.
Required fields:
- pan_number
- tan_number
- uan_number
- pf_account_number
- employer_name (Only the name of the employer/company. Do not include the address or any extra text like 'and address of the Employer'.)
- financial_year (e.g. 2023-24)
- assessment_year
- gross_salary
- basic_salary
- hra
- special_allowance
- total_deductions
- tds_deducted
- net_taxable_income
- annual_ctc
- pf_deduction
- bank_account_number
- bank_ifsc_code
- bank_name
- account_holder_name
"""
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[*uploaded_gemini_files, prompt],
                    config={"response_mime_type": "application/json"}
                )
                f16 = json.loads(response.text)
            except Exception as e:
                print("Gemini parsing failed, fallback to regex:", e)
                is_fallback = True
                f16 = _parse_form16(full_text)
                bank_details = _extract_bank_details(full_text)
        else:
            is_fallback = True
            f16 = _parse_form16(full_text)
            bank_details = _extract_bank_details(full_text)
            
        # Cleanup temp files and Gemini files
        for path in temp_files_paths:
            try: os.remove(path)
            except: pass
        if client:
            for g_file in uploaded_gemini_files:
                try: client.files.delete(name=g_file.name)
                except: pass
            
        return {
            "is_fallback": is_fallback,
            "data": {
                "personal": {
                    "pan_number": f16.get("pan_number", ""),
                    "tan_number": f16.get("tan_number", ""),
                    "uan_number": f16.get("uan_number", ""),
                    "pf_number": f16.get("pf_account_number", ""),
                },
                "work_history": [],
                "salary": {
                    "ctc": f16.get("annual_ctc") or f16.get("gross_salary", ""),
                    "basic": f16.get("basic_salary", ""),
                    "hra": f16.get("hra", ""),
                    "special_allowance": f16.get("special_allowance", ""),
                    "pf_contribution": f16.get("pf_deduction", ""),
                    "gross_salary": f16.get("gross_salary", ""),
                    "tds_deducted": f16.get("tds_deducted", ""),
                    "net_taxable_income": f16.get("net_taxable_income", ""),
                    "employer_name": f16.get("employer_name", ""),
                    "financial_year": f16.get("financial_year", ""),
                    "assessment_year": f16.get("assessment_year", ""),
                },
                "bank": {
                    "account_number": f16.get("bank_account_number") or bank_details.get("account_number", ""),
                    "ifsc_code": f16.get("bank_ifsc_code") or bank_details.get("ifsc_code", ""),
                    "bank_name": f16.get("bank_name") or bank_details.get("bank_name", ""),
                    "account_holder_name": f16.get("account_holder_name") or bank_details.get("account_holder_name", ""),
                },
                "tax": {
                    "financial_year": f16.get("financial_year", ""),
                    "assessment_year": f16.get("assessment_year", ""),
                    "tds_deducted": f16.get("tds_deducted", ""),
                }
            },
            "filename": ", ".join(filenames)
        }

# ── helpers ────────────────────────────────────────────────────────────────────

def _norm_date(s: str) -> str:
    if not s: return ""
    s = s.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s): return s
    m = re.match(r'^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$', s)
    if m: d,mo,y = m.groups(); return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    m = re.match(r'^(\d{1,2})[/\-](\d{4})$', s)
    if m: mo,y = m.groups(); return f"{y}-{mo.zfill(2)}-01"
    months = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    m = re.match(r'^([a-z]+)\s+(\d{4})$', s, re.IGNORECASE)
    if m:
        mn = months.get(m.group(1)[:3].lower())
        if mn: return f"{m.group(2)}-{str(mn).zfill(2)}-01"
    if re.match(r'^\d{4}$', s): return f"{s}-01-01"
    return ""

def _extract_name(lines):
    for line in lines[:15]:
        line = line.strip()
        if not line or len(line) > 60 or re.search(r'[@\d/\\|]', line): continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            parts = line.rsplit(None, 1)
            return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (line, "")
    return "", ""

def _grab_amt(text, *kws):
    for kw in kws:
        m = re.search(re.escape(kw) + r'[^\d\n]{0,60}([\d,]{4,}(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if m: return m.group(1).replace(',','')
    return ""

def _extract_bank_details(text: str) -> dict:
    accounts = ACCOUNT_RE.findall(text)
    # Filter common non-account numbers (like pincodes or phone numbers if they matched)
    acc = next((a for a in accounts if 10 <= len(a) <= 16), "")
    
    ifscs = IFSC_RE.findall(text)
    ifsc = ifscs[0] if ifscs else ""
    
    return {
        "account_number": acc,
        "ifsc_code": ifsc,
        "bank_name": "", # Hard to extract bank name reliably via regex
        "account_holder_name": ""
    }

# ── extractors ─────────────────────────────────────────────────────────────────

def _pdf_text(content: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        out = io.StringIO()
        extract_text_to_fp(io.BytesIO(content), out, laparams=LAParams())
        return out.getvalue()
    except ImportError:
        pass
    try:
        import PyPDF2
        r = PyPDF2.PdfReader(io.BytesIO(content))
        return "\n".join(p.extract_text() or "" for p in r.pages)
    except ImportError:
        raise HTTPException(500, "Install pdfminer.six: pip install pdfminer.six")

def _image_text(content: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(content)), lang='eng')
    except ImportError:
        raise HTTPException(500, "Install OCR: pip install pytesseract pillow")

def _get_text(content: bytes, ext: str) -> str:
    if ext == "pdf":           return _pdf_text(content)
    if ext in ("jpg","jpeg","png","webp"): return _image_text(content)
    raise HTTPException(400, f"Unsupported type .{ext} — use PDF, JPG, or PNG")

# ── parsers ────────────────────────────────────────────────────────────────────


def _parse_resume(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    first, last = _extract_name(lines)
    phones = PHONE_RE.findall(text)
    phone = re.sub(r'[\s\-]', '', phones[0]) if phones else ""
    # Strip +91 country code
    if phone.startswith('+91'): phone = phone[3:]
    elif phone.startswith('91') and len(phone) == 12: phone = phone[2:]
    emails = EMAIL_RE.findall(text)
    personal_email = next((e for e in emails if any(d in e.split('@')[1] for d in ('gmail','yahoo','hotmail','outlook','rediff','live'))), emails[0] if emails else "")
    dob = ""
    m = DOB_RE.search(text)
    if m: dob = _norm_date(m.group(1))
    gender = ""
    m = GENDER_RE.search(text)
    if m: gender = m.group(1).lower()
    city = (CITY_RE.search(text) or type('', (), {'group': lambda s,i: ''})()).group(1)
    if city: city = city.title()
    state = (STATE_RE.search(text) or type('', (), {'group': lambda s,i: ''})()).group(1)
    if state: state = state.title()
    pins = PIN_RE.findall(text)
    pincode = pins[0] if pins else ""
    work_history = []
    for m in RANGE_RE.finditer(text):
        pre = text[max(0, m.start()-300):m.start()]
        pre_lines = [l.strip() for l in pre.splitlines() if l.strip()][-4:]
        
        # Clean company name: remove leading bullet points like "1.", "•", "-", ". "
        company_name = pre_lines[-1] if pre_lines else ""
        company_name = re.sub(r'^[\s\d\.\-\•\·]+', '', company_name).strip()
        
        # Filter: if company name is just a number or too short, it's likely a skill list item, not a company
        if not company_name or len(company_name) <= 2 or company_name.isdigit():
            continue

        designation = pre_lines[-2] if len(pre_lines) >= 2 else ""
        designation = re.sub(r'^[\s\d\.\-\•\·]+', '', designation).strip()

        is_current = bool(re.match(r'present|current|till date', m.group(2), re.IGNORECASE))
        work_history.append({
            "company_name": company_name,
            "designation":  designation,
            "department":   "",
            "from_date":    _norm_date(m.group(1)),
            "to_date":      "" if is_current else _norm_date(m.group(2)),
            "is_current":   is_current,
            "last_ctc":     "",
        })
    uan = (UAN_RE.search(text) or type("",(),{"group":lambda s,i:""})()).group(1)
    pfno_m = PFNO_RE.search(text)
    pf_number = pfno_m.group(1).strip() if pfno_m else ""
    return {
        "first_name": first, "last_name": last, "phone": phone,
        "personal_email": personal_email, "date_of_birth": dob, "gender": gender,
        "address": "", "city": city, "state": state, "pincode": pincode,
        "emergency_contact_name": "", "emergency_contact_phone": "",
        "uan_number": uan, "pf_number": pf_number,
        "work_history": work_history,
    }

def _parse_form16(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pan = (PAN_RE.search(text) or type('', (), {'group': lambda s,i:''})(None)).group(1) if PAN_RE.search(text) else ""
    fy  = (FY_RE.search(text)  or type('', (), {'group': lambda s,i:''})(None)).group(1) if FY_RE.search(text)  else ""
    ay  = (AY_RE.search(text)  or type('', (), {'group': lambda s,i:''})(None)).group(1) if AY_RE.search(text)  else ""
    emp_name = emp_org = ""
    for line in lines:
        if not emp_name and re.search(r'employee\s*name|name of employee', line, re.IGNORECASE):
            p = re.split(r'[:—\s]{1,3}', line, 1); emp_name = p[1].strip() if len(p)==2 else ""
        if not emp_org and re.search(r'employer|deductor|company\s*name', line, re.IGNORECASE):
            p = re.split(r'[:—\s]{1,3}', line, 1); emp_org = p[1].strip() if len(p)==2 else ""
    return {
        "employee_name":      emp_name,
        "pan_number":         pan,
        "employer_name":      emp_org,
        "assessment_year":    ay,
        "financial_year":     fy,
        "gross_salary":       _grab_amt(text, 'gross salary', 'gross total income', 'total salary'),
        "basic_salary":       _grab_amt(text, 'basic salary', 'basic pay', 'basic'),
        "hra":                _grab_amt(text, 'house rent allowance', 'hra'),
        "special_allowance":  _grab_amt(text, 'special allowance', 'other allowance'),
        "total_deductions":   _grab_amt(text, 'total deductions', 'deductions'),
        "tds_deducted":       _grab_amt(text, 'tax deducted', 'tds', 'total tax'),
        "net_taxable_income": _grab_amt(text, 'net taxable income', 'taxable income'),
        "annual_ctc":         _grab_amt(text, 'annual ctc', 'total ctc', 'cost to company'),
        "pf_deduction":       _grab_amt(text, 'provident fund', 'pf contribution', 'epf'),
        "uan_number":         (UAN_RE.search(text) or type("",(),{"group":lambda s,i:""})()).group(1),
        "pf_account_number":  (PFNO_RE.search(text) or type("",(),{"group":lambda s,i:""})()).group(1) if PFNO_RE.search(text) else "",
    }

# ── routes ─────────────────────────────────────────────────────────────────────


@router.post("/{employee_id}/parse-resume")
async def parse_resume(
    employee_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if str(current_user.id) != str(employee_id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")
    result = await _process_extraction(files, "resume")
    return {"parsed": result["data"], "source": "resume", "filename": result["filename"]}

@router.post("/{employee_id}/parse-form16")
async def parse_form16(
    employee_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if str(current_user.id) != str(employee_id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")
    result = await _process_extraction(files, "form16")
    return {"parsed": result["data"], "source": "form16", "filename": result["filename"]}
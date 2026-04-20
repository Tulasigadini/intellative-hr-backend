# Intellativ HR & IAM System

HR Onboarding + Identity & Access Management platform built with **FastAPI** + **React**.

---

## Project Structure

```
intellativ-hr-backend/
├── main.py
├── requirements.txt
├── .env.example
└── app/
    ├── api/routes/
    │   ├── auth.py
    │   ├── departments.py      # dept + role routes
    │   ├── employees.py
    │   └── iam.py
    ├── core/
    │   ├── config.py
    │   ├── deps.py             # auth dependency
    │   └── security.py        # JWT + bcrypt
    ├── db/
    │   └── database.py
    ├── models/
    │   └── models.py           # SQLAlchemy ORM models
    ├── schemas/
    │   └── schemas.py          # Pydantic schemas
    ├── services/
    │   ├── email_service.py
    │   └── employee_service.py
    └── utils/
        └── seed.py             # seed script

intellativ-hr-frontend/
├── package.json
├── .env.example
├── public/
│   └── index.html
└── src/
    ├── App.js
    ├── index.js
    ├── assets/styles/
    │   └── global.css
    ├── components/layout/
    │   └── Layout.jsx
    ├── hooks/
    │   └── useAuth.js
    ├── pages/
    │   ├── LoginPage.jsx
    │   ├── DashboardPage.jsx
    │   ├── OnboardingPage.jsx  # 5-step wizard
    │   ├── EmployeesPage.jsx
    │   ├── EmployeeDetailPage.jsx
    │   ├── DepartmentsPage.jsx
    │   ├── RolesPage.jsx       # tree + list view
    │   └── IAMPage.jsx
    └── services/
        └── api.js              # axios service layer
```

---

## Backend Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 14+

### Installation

```bash
# 1. Clone and enter backend directory
cd intellativ-hr-backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, SMTP credentials

# 5. Create PostgreSQL database
psql -U postgres -c "CREATE DATABASE intellativ_hr;"

# 6. Seed default data (departments, IT roles, admin user)
python -m app.utils.seed

# 7. Run server
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs  
Default admin: `admin@intellativ.com` / `Admin@123`

---

## Frontend Setup

### Prerequisites
- Node.js 18+
- npm 9+

### Installation

```bash
# 1. Enter frontend directory
cd intellativ-hr-frontend

# 2. Install dependencies
npm install

# 3. Configure environment
cp .env.example .env
# Set REACT_APP_API_URL=http://localhost:8000/api/v1

# 4. Start development server
npm start
```

App runs at: http://localhost:3000

---

## Features

| Feature | Description |
|---|---|
| Employee Onboarding | 5-step wizard: type → personal → job → docs → activate |
| New / Rejoining Detection | Handles both flows with previous employment fields |
| Role Hierarchy | IT dept: 20+ roles across 7 levels; tree visualization |
| IAM | User accounts, enable/disable, password reset, system access rules |
| Email Notifications | Welcome email on activation, asset & relieving alerts |
| Document Management | Upload Aadhar, PAN, Passport, Degree, etc. per employee |
| Asset Tracking | Email HR on joining/relieving for laptop allocation/collection |
| Employee ID Generation | Auto-generated unique IDs like `INT24IT3F2A` |
| Company Email Generation | Auto-generated `firstname.lastname@intellativ.com` |
| Dashboard | Live stats + bar chart + pie chart + recent employees |
| Responsive | Works on desktop, tablet, mobile |

---

## Default IT Roles (seeded)

```
CTO (L1)
└── VP Engineering (L2)
    ├── Cloud Architect (L4)
    ├── Security Engineer (L5)
    └── Engineering Manager (L3)
        ├── Technical Lead (L4)
        │   ├── Senior Software Engineer (L5)
        │   ├── Software Engineer (L5)
        │   │   └── Junior Software Engineer (L6)
        │   │       └── Intern (L7)
        │   ├── DevOps Engineer (L4)
        │   ├── Data Engineer (L5)
        │   ├── Data Scientist (L5)
        │   ├── ML Engineer (L5)
        │   └── QA Engineer (L5)
        ├── UI/UX Designer (L5)
        ├── Business Analyst (L5)
        └── Project Manager (L4)
            └── Scrum Master (L5)
```

---

## API Endpoints

```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh

GET    /api/v1/departments
POST   /api/v1/departments
PUT    /api/v1/departments/{id}
DELETE /api/v1/departments/{id}

GET    /api/v1/roles
GET    /api/v1/roles/tree
POST   /api/v1/roles
PUT    /api/v1/roles/{id}
DELETE /api/v1/roles/{id}

GET    /api/v1/employees
POST   /api/v1/employees
GET    /api/v1/employees/{id}
PUT    /api/v1/employees/{id}
POST   /api/v1/employees/{id}/activate
POST   /api/v1/employees/{id}/relieve
POST   /api/v1/employees/{id}/documents
GET    /api/v1/employees/{id}/documents
POST   /api/v1/employees/{id}/profile-picture
GET    /api/v1/employees/dashboard/stats

GET    /api/v1/iam/accounts
PUT    /api/v1/iam/accounts/{id}/toggle
PUT    /api/v1/iam/accounts/{id}/reset-password
GET    /api/v1/iam/system-accesses
POST   /api/v1/iam/system-accesses
DELETE /api/v1/iam/system-accesses/{id}
```

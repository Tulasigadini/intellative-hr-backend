### postgres
    # psql -U postgres -d intellativ_hr
    # access100

### migration commands
    
    ## Create first migration (baseline of existing tables)
        # python -m alembic stamp head   (do not use this command, use below 2 commands)

    ## Generate migration for new columns
        # python -m  alembic revision --autogenerate -m "add_onboarded_by_to_employees"

    ## Apply the migration
        # python -m alembic upgrade head


## sample data population
    # python -m app.utils.seed

# -- ── 1. employees table ────────────────────────────────────────────────────────
# ALTER TABLE employees
#   ADD COLUMN IF NOT EXISTS onboarded_by UUID REFERENCES employees(id),
#   ADD COLUMN IF NOT EXISTS onboarded_by_email VARCHAR(255);

# -- ── 2. notifications table ────────────────────────────────────────────────────
# -- Rename recipient_id → recipient_employee_id (if not done yet)
# DO $$
# BEGIN
#   IF EXISTS (SELECT 1 FROM information_schema.columns
#     WHERE table_name='notifications' AND column_name='recipient_id') THEN
#     ALTER TABLE notifications RENAME COLUMN recipient_id TO recipient_employee_id;
#   END IF;
# END $$;

# ALTER TABLE notifications
#   ADD COLUMN IF NOT EXISTS notification_type VARCHAR(50),
#   ADD COLUMN IF NOT EXISTS action_url VARCHAR(500),
#   ADD COLUMN IF NOT EXISTS related_employee_id UUID REFERENCES employees(id);

# -- ── 3. work_history table ─────────────────────────────────────────────────────
# CREATE TABLE IF NOT EXISTS work_history (
#   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#   employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
#   company_name VARCHAR(200) NOT NULL,
#   designation VARCHAR(200),
#   department VARCHAR(200),
#   from_date DATE,
#   to_date DATE,
#   reason_for_leaving VARCHAR(500),
#   last_ctc VARCHAR(50),
#   is_intellativ BOOLEAN DEFAULT FALSE,
#   created_at TIMESTAMP DEFAULT NOW()
# );

# -- ── 4. insurance_info table ───────────────────────────────────────────────────
# CREATE TABLE IF NOT EXISTS insurance_info (
#   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#   employee_id UUID UNIQUE NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
#   nominee_name VARCHAR(200),
#   nominee_relation VARCHAR(100),
#   nominee_dob DATE,
#   nominee_phone VARCHAR(20),
#   blood_group VARCHAR(10),
#   pre_existing_conditions TEXT,
#   submitted BOOLEAN DEFAULT FALSE,
#   submitted_at TIMESTAMP,
#   created_at TIMESTAMP DEFAULT NOW(),
#   updated_at TIMESTAMP DEFAULT NOW()
# );

# -- ── 5. onboarding_steps table ─────────────────────────────────────────────────
# CREATE TABLE IF NOT EXISTS onboarding_steps (
#   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#   employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
#   step_name VARCHAR(100),
#   step_code VARCHAR(50),
#   is_completed BOOLEAN DEFAULT FALSE,
#   completed_at TIMESTAMP,
#   notes TEXT,
#   created_at TIMESTAMP DEFAULT NOW()
# );
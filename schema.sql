-- Digital Risk Shield schema. Paste into Supabase: SQL Editor > New query > Run.
create table if not exists brands (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  official_website text,
  created_at timestamptz not null default now()
);

create table if not exists official_assets (
  id uuid primary key default gen_random_uuid(),
  brand_id uuid not null references brands(id) on delete cascade,
  asset_type text not null check (asset_type in ('social', 'app')),
  official_identifier text not null,      -- username or app name
  official_publisher text,                -- optional, used for apps
  created_at timestamptz not null default now()
);

create table if not exists scan_results (
  id uuid primary key default gen_random_uuid(),
  brand_id uuid not null references brands(id) on delete cascade,
  scan_type text not null check (scan_type in ('social', 'app')),
  submitted_identifier text not null,
  platform text,
  risk_score integer not null check (risk_score between 0 and 100),
  risk_level text not null check (risk_level in ('Low', 'Medium', 'High', 'Critical')),
  reasons jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_assets_brand on official_assets (brand_id);
create index if not exists idx_scans_created on scan_results (created_at desc);

-- Access control: turn on Row Level Security and add NO policies. The public "anon" key
-- (and any browser) is then denied everything. Only the backend's service-role key can
-- read/write, because that key bypasses RLS. Keep that key server-side only.
alter table brands enable row level security;
alter table official_assets enable row level security;
alter table scan_results enable row level security;

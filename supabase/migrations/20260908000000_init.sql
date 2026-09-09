-- ארון בהתאמה — סכמה ראשונית (PostgreSQL / Supabase)
-- מזהים: UUID שנוצרים בשרת. זמנים: timestamptz ב-UTC. כסף: numeric(12,2).
-- אותו קובץ מותאם ל-SQLite בזמן ריצה (app/repositories/sql_dialect.py).

create table if not exists admin_users (
  id            uuid primary key,
  auth_user_id  uuid not null unique,          -- מזהה המשתמש ב-Supabase Auth
  email         text not null unique,
  display_name  text not null,
  active        boolean not null default true,
  created_at    timestamptz not null
);

create table if not exists customers (
  id          uuid primary key,
  full_name   text not null check (length(full_name) between 2 and 120),
  phone       text not null check (length(phone) between 7 and 20),
  email       text,
  city        text,
  created_at  timestamptz not null,
  updated_at  timestamptz not null
);
create index if not exists customers_phone_idx on customers (phone);

create table if not exists inquiries (
  id                      uuid primary key,
  number                  text not null unique,                 -- למשל AB-2026-0042
  customer_id             uuid references customers(id),
  status                  text not null check (status in (
                            'collecting_details','awaiting_carpenter','quote_available',
                            'change_requested','accepted','closed')),
  current_spec_version    integer not null default 1,
  requires_manual_review  boolean not null default false,
  manual_review_reasons   jsonb not null default '[]',
  contact_name            text,
  contact_phone           text,
  contact_email           text,
  contact_city            text,
  submitted_at            timestamptz,
  closed_at               timestamptz,
  row_version             integer not null default 1,           -- לנעילה אופטימית
  created_at              timestamptz not null,
  updated_at              timestamptz not null
);
create index if not exists inquiries_status_idx on inquiries (status);
create index if not exists inquiries_customer_idx on inquiries (customer_id);
create index if not exists inquiries_created_idx on inquiries (created_at desc);

create table if not exists conversations (
  id          uuid primary key,
  inquiry_id  uuid not null unique references inquiries(id) on delete cascade,
  provider    text not null check (provider in ('openai','mock')),
  created_at  timestamptz not null
);

create table if not exists messages (
  id               uuid primary key,
  conversation_id  uuid not null references conversations(id) on delete cascade,
  role             text not null check (role in ('user','assistant','system')),
  content          text not null check (length(content) <= 4000),
  meta             jsonb not null default '{}',                -- למשל simulated, missing_fields
  created_at       timestamptz not null
);
create index if not exists messages_conversation_idx on messages (conversation_id, created_at);

-- כל גרסת מפרט נשמרת כשורה נפרדת; הגרסה הנוכחית מסומנת ב-inquiries.current_spec_version
create table if not exists wardrobe_specs (
  id                  uuid primary key,
  inquiry_id          uuid not null references inquiries(id) on delete cascade,
  version             integer not null check (version >= 1),
  spec                jsonb not null,
  missing_fields      jsonb not null default '[]',
  customer_confirmed  boolean not null default false,
  source              text not null check (source in ('customer_form','ai','carpenter','system')),
  actor_id            text,
  created_at          timestamptz not null,
  unique (inquiry_id, version)
);

create table if not exists catalog_items (
  id              uuid primary key,
  kind            text not null check (kind in ('body_material','front_material','finish','delivery_zone')),
  code            text not null unique,
  name_he         text not null,
  description_he  text,
  active          boolean not null default true,
  sort_order      integer not null default 0
);

-- מחירון: כל שמירה יוצרת גרסה חדשה; הצעות שומרות snapshot ואינן משתנות
create table if not exists price_books (
  id          uuid primary key,
  version     integer not null unique check (version >= 1),
  is_demo     boolean not null default false,
  is_active   boolean not null default false,
  settings    jsonb not null,
  created_by  text,
  created_at  timestamptz not null
);

create table if not exists price_book_items (
  id                   uuid primary key,
  price_book_id        uuid not null references price_books(id) on delete cascade,
  code                 text not null,
  category             text not null check (category in (
                         'material','back_material','finish','hardware','drawer','labor','delivery','service')),
  name_he              text not null,
  unit                 text not null,
  unit_price           numeric(12,2) not null check (unit_price >= 0),
  active               boolean not null default true,
  includes_soft_close  boolean not null default false,
  description_he       text,
  unique (price_book_id, code)
);

create table if not exists quotes (
  id                   uuid primary key,
  inquiry_id           uuid not null references inquiries(id) on delete cascade,
  version              integer not null check (version >= 1),
  status               text not null check (status in (
                         'draft','published','accepted','superseded','expired','cancelled')),
  spec_version         integer not null,
  spec_snapshot        jsonb not null,
  pricing_snapshot     jsonb not null,                          -- PricingResult מלא
  adjustments          jsonb not null default '[]',
  delivery_zone_code   text,
  subtotal             numeric(12,2),
  vat_rate             numeric(6,4) not null,
  vat_amount           numeric(12,2),
  total                numeric(12,2) check (total is null or total >= 0),
  currency             text not null default 'ILS',
  terms_he             text,
  manual_handled       boolean not null default false,         -- הנגר טיפל בכל הדרישות הידניות
  is_stale             boolean not null default false,         -- המפרט שונה אחרי החישוב
  change_request_text  text,
  published_at         timestamptz,
  expires_at           timestamptz,
  accepted_at          timestamptz,
  cancelled_at         timestamptz,
  row_version          integer not null default 1,
  created_at           timestamptz not null,
  updated_at           timestamptz not null,
  unique (inquiry_id, version)
);
create index if not exists quotes_inquiry_idx on quotes (inquiry_id, version desc);
create index if not exists quotes_status_idx on quotes (status);

create table if not exists quote_items (
  id           uuid primary key,
  quote_id     uuid not null references quotes(id) on delete cascade,
  position     integer not null,
  code         text not null,
  description  text not null,
  quantity     numeric(12,3) not null,
  unit         text not null,
  unit_price   numeric(12,2) not null,
  total        numeric(12,2) not null,
  kind         text not null check (kind in ('auto','manual')),
  reason       text
);
create index if not exists quote_items_quote_idx on quote_items (quote_id, position);

create table if not exists internal_notes (
  id          uuid primary key,
  inquiry_id  uuid not null references inquiries(id) on delete cascade,
  author_id   text not null,
  body        text not null check (length(body) between 1 and 4000),
  created_at  timestamptz not null
);

-- יומן אירועים: מי עשה מה ומתי
create table if not exists inquiry_events (
  id          uuid primary key,
  inquiry_id  uuid not null references inquiries(id) on delete cascade,
  event_type  text not null,
  actor_type  text not null check (actor_type in ('customer','carpenter','system','ai')),
  actor_id    text,
  payload     jsonb not null default '{}',
  created_at  timestamptz not null
);
create index if not exists inquiry_events_inquiry_idx on inquiry_events (inquiry_id, created_at);

-- קישור גישה אישי: נשמר רק hash של הטוקן
create table if not exists customer_access_tokens (
  id            uuid primary key,
  inquiry_id    uuid not null references inquiries(id) on delete cascade,
  token_hash    text not null unique,
  expires_at    timestamptz not null,
  revoked_at    timestamptz,
  last_used_at  timestamptz,
  created_at    timestamptz not null
);

-- RLS: מופעל על כל הטבלאות, ללא policies ציבוריות. השרת עובד עם service role
-- ומבצע בדיקות הרשאה מפורשות בכל endpoint.
alter table admin_users enable row level security;
alter table customers enable row level security;
alter table inquiries enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;
alter table wardrobe_specs enable row level security;
alter table catalog_items enable row level security;
alter table price_books enable row level security;
alter table price_book_items enable row level security;
alter table quotes enable row level security;
alter table quote_items enable row level security;
alter table internal_notes enable row level security;
alter table inquiry_events enable row level security;
alter table customer_access_tokens enable row level security;

-- Jalankan di Supabase > SQL Editor
create extension if not exists pgcrypto;
create table students (nim text primary key, name text not null, major text);
create table users (id uuid primary key default gen_random_uuid(), nim text unique, phone text unique,
  name text not null, role text not null check (role in ('student','guest')), created_at timestamptz default now());
create table workspaces (id uuid primary key default gen_random_uuid(), code text unique not null, name text not null,
  zone text not null, seats int default 1, sensor_present boolean default false, distance_cm real, last_seen timestamptz);
create table sessions (id uuid primary key default gen_random_uuid(), workspace_id uuid references workspaces(id),
  user_id uuid references users(id), started_at timestamptz default now(), ended_at timestamptz);
create unique index one_active_per_ws on sessions(workspace_id) where ended_at is null;
create unique index one_active_per_user on sessions(user_id) where ended_at is null;
create table otp_codes (id uuid primary key default gen_random_uuid(), phone text not null, code_hash text not null,
  expires_at timestamptz not null, used boolean default false, created_at timestamptz default now());
alter table students enable row level security; alter table users enable row level security;
alter table workspaces enable row level security; alter table sessions enable row level security;
alter table otp_codes enable row level security;  -- server memakai service_role key (bypass RLS)

insert into students values ('2021001','Alya Putri','Informatika'),('2021002','Bima Pratama','Teknik Elektro'),('2021003','Citra Dewi','Sistem Informasi');
insert into workspaces (code,name,zone) values
('WS-A01','Meja A1','Perpustakaan'),('WS-A02','Meja A2','Perpustakaan'),('WS-A03','Meja A3','Perpustakaan'),('WS-A04','Meja A4','Perpustakaan'),
('WS-B01','Bilik B1','Co-Working Lt.2'),('WS-B02','Bilik B2','Co-Working Lt.2'),('WS-B03','Bilik B3','Co-Working Lt.2'),
('WS-C01','Sofa C1','Kantin Kreatif'),('WS-C02','Sofa C2','Kantin Kreatif'),('WS-C03','Sofa C3','Kantin Kreatif');

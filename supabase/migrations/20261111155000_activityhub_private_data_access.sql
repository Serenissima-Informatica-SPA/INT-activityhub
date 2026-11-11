-- Private storage for Activity Hub exports. Applied to project khlgxvabdtnpnsabdhlu.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('activityhub-data', 'activityhub-data', false, 52428800, array['application/gzip'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

create table if not exists public.activityhub_access (
  user_id uuid primary key references auth.users(id) on delete cascade,
  enabled boolean not null default false,
  created_at timestamptz not null default now()
);

alter table public.activityhub_access enable row level security;

drop policy if exists "Users can read their own enabled access" on public.activityhub_access;
create policy "Users can read their own enabled access"
on public.activityhub_access
for select
to authenticated
using (user_id = auth.uid() and enabled = true);

drop policy if exists "Enabled Activity Hub users can read private exports" on storage.objects;
create policy "Enabled Activity Hub users can read private exports"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'activityhub-data'
  and exists (
    select 1
    from public.activityhub_access access
    where access.user_id = auth.uid()
      and access.enabled = true
  )
);

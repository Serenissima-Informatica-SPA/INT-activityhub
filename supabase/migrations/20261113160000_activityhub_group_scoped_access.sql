-- Scopes for Activity Hub private exports.
-- Existing enabled users keep full access via the default "all" scope.
alter table public.activityhub_access
  add column if not exists access_scope text not null default 'all';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'activityhub_access_scope_check'
      and conrelid = 'public.activityhub_access'::regclass
  ) then
    alter table public.activityhub_access
      add constraint activityhub_access_scope_check
      check (access_scope in ('all', 'DEV'));
  end if;
end
$$;

drop policy if exists "Enabled Activity Hub users can read private exports" on storage.objects;
drop policy if exists "Enabled Activity Hub users can read scoped private exports" on storage.objects;
create policy "Enabled Activity Hub users can read scoped private exports"
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
      and (
        access.access_scope = 'all'
        or (
          access.access_scope = 'DEV'
          and name = 'DEV/activity-logs.json.gz'
        )
      )
  )
);
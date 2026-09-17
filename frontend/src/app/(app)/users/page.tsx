import type { Metadata } from "next";

import { CreateUserDialog } from "@/components/shared/create-user-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow, TableWrap,
} from "@/components/ui/table";
import { api, apiSafe } from "@/lib/api";
import { can, getSessionUser } from "@/lib/session";
import { formatDate, relativeTime } from "@/lib/format";
import type { Paged, SessionUser } from "@/lib/types";

export const metadata: Metadata = { title: "Users" };

interface Role {
  name: string;
  label: string;
  description: string;
  permissions: string[];
}

export default async function UsersPage() {
  const user = await getSessionUser();
  const [users, roles] = await Promise.all([
    api<Paged<SessionUser>>("/users", { searchParams: { page_size: 100 } }),
    apiSafe<Role[]>("/auth/roles"),
  ]);

  return (
    <>
      <PageHeader
        title="Users & roles"
        description="Authorisation is enforced server side on every endpoint. The role matrix below is the
          same one the API checks — the interface only uses it to hide controls a role cannot use."
        actions={can(user, "user:write") ? <CreateUserDialog roles={roles ?? []} /> : null}
      />

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-xs font-semibold">Roles</h2>
          <span className="text-2xs text-muted-foreground">
            Separation of duties: the officer who decides a claim is not the reviewer who adjudicates
            its findings
          </span>
        </header>
        <div className="grid gap-3 p-4 md:grid-cols-2">
          {(roles ?? []).map((role) => (
            <div key={role.name} className="rounded-md border bg-muted/30 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold">{role.label}</p>
                <Badge variant="muted">{role.permissions.length} permissions</Badge>
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-muted-foreground">
                {role.description}
              </p>
              <details className="mt-2">
                <summary className="cursor-pointer text-2xs text-muted-foreground">
                  Permission list
                </summary>
                <ul className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5">
                  {role.permissions.map((permission) => (
                    <li key={permission} className="font-mono text-2xs text-muted-foreground">
                      {permission}
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-xs font-semibold">Accounts</h2>
          <Badge variant="muted">{users.meta.total}</Badge>
        </header>
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Job title</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last sign-in</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.items.length === 0 && <TableEmpty colSpan={8}>No users.</TableEmpty>}
              {users.items.map((account) => (
                <TableRow key={account.id}>
                  <TableCell className="text-xs font-medium">{account.full_name}</TableCell>
                  <TableCell className="font-mono text-2xs">{account.email}</TableCell>
                  <TableCell>
                    <Badge variant="default">{account.role_label ?? account.role_name}</Badge>
                  </TableCell>
                  <TableCell className="text-2xs text-muted-foreground">
                    {account.job_title ?? "—"}
                  </TableCell>
                  <TableCell className="text-2xs text-muted-foreground">
                    {account.team ?? "—"}
                  </TableCell>
                  <TableCell>
                    {account.is_active ? (
                      <Badge variant="low">Active</Badge>
                    ) : (
                      <Badge variant="high">Disabled</Badge>
                    )}
                    {account.must_change_password && (
                      <Badge variant="review" className="ml-1">
                        Must change password
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                    {account.last_login_at ? relativeTime(account.last_login_at) : "never"}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-2xs text-muted-foreground">
                    {formatDate(account.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
      </section>
    </>
  );
}

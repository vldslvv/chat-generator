# One-to-one chat prototype

Build a web chat prototype for exchanging text messages between predefined users.

- Implement the application at `apps/chat`, relative to the repository root.
- Seed the users `user1`, `user2`, and `user3` without registration or passwords.
- Select the current identity by login name without verifying ownership of that name.
- Support one active browser client per user and one selected recipient per client.
- Use Svelte, TypeScript, Vite, and plain CSS for the web client.
- Use FastAPI and Uvicorn for the API.
- Persist users, messages, and delivery timestamps in Postgres.
- Run web, API, and database services through Docker Compose.
- Serve compiled web assets through Nginx and proxy `/api` to the API service.
- Keep Postgres data in a named volume across ordinary service restarts.
- Implement polling first and leave push delivery for a later specification revision.
- Exclude attachments, editing, deletion, typing indicators, read receipts, and user management.
- Treat [API behavior](contracts/api.md) and [database behavior](contracts/database.md) as authoritative shared contracts.
- Follow [task order](task_order.md) and verify the assembled application against [shared scenarios](verification.md).

## Specification boundary

Apply when implementing this bundle.

- Keep contracts separate from [component tasks](task_order.md).
- Link each provider and consumer task to its applicable contracts.
- Keep shared requirements in their contracts instead of copying them into tasks.
- Treat acknowledgment as confirmation of client display rather than human reading.
- Accept possible duplicate messages when manually retrying a send whose response was lost.

## Implementation suggestions

Apply these advisory choices when implementing the components.

- Use Psycopg with parameterized SQL in a small database-access module.
- Initialize the schema and seed users through a Postgres initialization script.
- Use a build stage for frontend dependencies and serve only compiled assets at runtime.

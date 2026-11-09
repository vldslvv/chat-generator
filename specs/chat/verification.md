# Verification

Apply these checks to the [component tasks](task_order.md), [API contract](contracts/api.md), and [database contract](contracts/database.md).

- Run storage and API integration checks against real Postgres.
- Run browser checks against the assembled web, API, and database services.
- Use isolated test data and remove only the test resources created by each scenario.
- Record commands and results for automated checks and steps and observations for manual browser checks.
- Treat unavailable required runtime checks as blocked app acceptance rather than passing document validation.

## Validation and isolation

- **Scenario:** Validate participants, content, and ownership.
- **Task/source clauses:** Database, API, and client tasks implement [validation](contracts/api.md#validation-and-errors) and [storage scoping](contracts/database.md#storage-operations).
- **Setup and inputs:** Seed the three users and create messages in the user1/user2 and user1/user3 conversations.
- **Actions:** Exercise history, polling, sending, and acknowledgment with valid names, unknown names, absent headers, self-chat, malformed IDs, and unrelated delivery IDs.
- **Pass rule:** Responses follow the error table, successful reads contain only the selected pair, and rejected mutations leave storage unchanged.
- **Pass rule:** Whitespace-only and 2,001-code-point text fail, while valid 2,000-code-point text and line breaks persist unchanged.
- **Pass rule:** The client renders markup-like message text literally without executing it.
- **Cleanup:** Remove the isolated test database and browser contexts.
- **Evidence:** API integration results and browser observations.

## History and backlog

- **Scenario:** Merge bounded history with an unbounded pending backlog.
- **Task/source clauses:** Database, API, and client tasks implement [history and polling](contracts/api.md#history-and-polling).
- **Setup and inputs:** Create 150 unacknowledged messages from user2 to user1 in an isolated conversation.
- **Actions:** Retrieve history and pending data, open the user1 chat, and repeat pending responses before acknowledgment completes.
- **Pass rule:** History returns the latest 100 records, pending returns all 150, and the browser displays 150 distinct messages in ascending ID order.
- **Pass rule:** New messages append without a display cap and displayed incoming messages are acknowledged.
- **Cleanup:** Remove the isolated test database and browser contexts.
- **Evidence:** Storage/API integration results and browser observations.

## Message delivery

- **Scenario:** Exchange a message and observe delivery.
- **Task/source clauses:** All tasks implement [sending and acknowledgment](contracts/api.md#sending-and-acknowledgment) and [client interaction](contracts/api.md#client-interaction).
- **Setup and inputs:** Start the assembled services and open separate browser contexts as user1 and user2 with each other as recipient.
- **Actions:** Send a message, observe recipient rendering, and inspect acknowledgment and the sender's subsequent poll.
- **Pass rule:** The message is persisted before Sent appears and Delivered appears after the first completed sender poll that observes acknowledgment.
- **Pass rule:** Before acknowledgment, pending requests repeat the message; after acknowledgment, they exclude it.
- **Pass rule:** Repeated and concurrent acknowledgment requests return the same timestamp without changing other message fields.
- **Pass rule:** Poll requests do not overlap, and the next scheduled poll starts two seconds after completion subject to browser scheduling.
- **Cleanup:** Close browser contexts and remove isolated test resources.
- **Evidence:** Browser network observations and API/storage integration results.

## Failure recovery

- **Scenario:** Recover from connection failures without silently retrying sends.
- **Task/source clauses:** Database, API, and client tasks implement [transaction failures](contracts/database.md#transactions-and-failures) and [client recovery](contracts/api.md#client-interaction).
- **Setup and inputs:** Open a conversation with saved messages and an unsent draft.
- **Actions:** Stop Postgres, attempt API operations, restore it, and interrupt browser responses for a send and an acknowledgment.
- **Pass rule:** Definite storage failures return `503`, visible history remains, and failed sends preserve the draft without automatic resend.
- **Pass rule:** Polling resumes after recovery and unconfirmed acknowledgments are retried when the server repeats pending messages.
- **Pass rule:** A committed send whose response was lost remains in history, and manually resending may create a second record.
- **Pass rule:** A committed acknowledgment whose response was lost retains its timestamp and is observable through later history or delivery lookup.
- **Cleanup:** Restore connectivity and remove isolated test resources.
- **Evidence:** Real-service interruption results and browser network observations.

## Persistence

- **Scenario:** Preserve data through service and browser restarts.
- **Task/source clauses:** Database and integration tasks implement [project persistence](project.md) and the [database contract](contracts/database.md).
- **Setup and inputs:** Start from an empty test volume and create both delivered and undelivered messages.
- **Actions:** Restart the Compose services without deleting the volume and reload the browser page.
- **Pass rule:** The three seed users remain unique and saved message fields and delivery timestamps remain unchanged.
- **Pass rule:** Reload shows the entry form and re-entering the same pair restores the contracted history and pending messages.
- **Cleanup:** Remove only the isolated test stack and its test volume.
- **Evidence:** Compose commands, database/API observations, and browser observations.

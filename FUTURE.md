# Future improvements

- Store users and messages in PostgreSQL and keep client queues across restarts.
- Add password login and secure session handling.
- Make delivery retries safe with stable message IDs and duplicate suppression.
- Add delivery notifications, keeping server acceptance separate from recipient receipt.
- Track delivery latency, queue age, and error rates.
- Load-test the app, then scale the API and delivery workers where needed.
- Consider a durable delivery system such as Kafka if traffic justifies it.
- Add transport and storage encryption, then design end-to-end encryption and key management.
- Extend the shared spec with a new feature, regenerate both clients, and verify they still work together.

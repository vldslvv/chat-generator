# Selected implementation usage

Null means unavailable. Known subtotals exclude missing measurements. Scope and omissions are in usage.json.

| Metric | Total | Known subtotal | Measured records | Missing records |
|---|---:|---:|---:|---:|
| input_tokens | 6223189 | 6223189 | 161 | 0 |
| cached_input_tokens | 5985280 | 5985280 | 161 | 0 |
| cache_write_input_tokens | 0 | 0 | 161 | 0 |
| uncached_input_tokens | 237909 | 237909 | 161 | 0 |
| output_tokens | 37466 | 37466 | 161 | 0 |
| reasoning_output_tokens | 5391 | 5391 | 161 | 0 |
| total_tokens | 6260655 | 6260655 | 161 | 0 |

## By task

| Group | Total tokens | Known subtotal | Missing records | Tools |
| --- | --- | --- | --- | --- |
| 01_api | 3478737 | 3478737 | 0 | 74 |
| orchestration | 1989079 | 1989079 | 0 | 58 |
| validation | 792839 | 792839 | 0 | 20 |

Attribution omissions: 0 events; 0 diagnostics.

## By agent_run

| Group | Total tokens | Known subtotal | Missing records | Tools |
| --- | --- | --- | --- | --- |
| codex:01a1bde7-e9fa-7351-a75a-a7326e6ff8c8 | 1989079 | 1989079 | 0 | 58 |
| codex:01a1bde9-516c-77b2-8ace-d113970d06c7 | 2355562 | 2355562 | 0 | 44 |
| codex:01a1bdf1-0425-7c72-b4ec-f7b2dca79eb7 | 564684 | 564684 | 0 | 15 |
| codex:01a1bdf4-ccc1-75a3-a732-2fefda66d3ee | 558491 | 558491 | 0 | 15 |
| codex:01a1bdf6-7034-7630-99b3-18999222de2b | 792839 | 792839 | 0 | 20 |

Attribution omissions: 0 events; 0 diagnostics.

## By role

| Group | Total tokens | Known subtotal | Missing records | Tools |
| --- | --- | --- | --- | --- |
| implementer | 2355562 | 2355562 | 0 | 44 |
| reviewer | 1123175 | 1123175 | 0 | 30 |
| supervisor | 1989079 | 1989079 | 0 | 58 |
| validator | 792839 | 792839 | 0 | 20 |

Attribution omissions: 0 events; 0 diagnostics.

## By model

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| gpt-6.1-sol | 6260655 | 6260655 | 0 |

Attribution omissions: 0 events; 6 diagnostics.

## By effort

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| medium | 6260655 | 6260655 | 0 |

Attribution omissions: 0 events; 6 diagnostics.

## By model_effort

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| gpt-6.1-sol, medium | 6260655 | 6260655 | 0 |

Attribution omissions: 0 events; 6 diagnostics.

## By task_model_effort

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| 01_api, gpt-6.1-sol, medium | 3478737 | 3478737 | 0 |
| orchestration, gpt-6.1-sol, medium | 1989079 | 1989079 | 0 |
| validation, gpt-6.1-sol, medium | 792839 | 792839 | 0 |

Attribution omissions: 0 events; 6 diagnostics.

## By tool

| Group | Observed calls | Outcomes | Observed seconds | Untimed |
| --- | --- | --- | --- | --- |
| exec | 88 | {'returned': 88} | 186.7099986076355 | 0 |
| followup_task | 1 | {'returned': 1} | 0.004999876022338867 | 0 |
| send_message | 29 | {'returned': 29} | 1.3500003814697266 | 0 |
| spawn_agent | 4 | {'returned': 4} | 0.2740001678466797 | 0 |
| wait_agent | 30 | {'returned': 30} | 891.2560000419617 | 0 |

Attribution omissions: 0 events; 6 diagnostics.

## By task_tool

| Group | Observed calls | Outcomes | Observed seconds | Untimed |
| --- | --- | --- | --- | --- |
| 01_api, exec | 60 | {'returned': 60} | 128.7899992465973 | 0 |
| 01_api, send_message | 14 | {'returned': 14} | 0.5940003395080566 | 0 |
| orchestration, exec | 11 | {'returned': 11} | 2.7689998149871826 | 0 |
| orchestration, followup_task | 1 | {'returned': 1} | 0.004999876022338867 | 0 |
| orchestration, send_message | 12 | {'returned': 12} | 0.5690000057220459 | 0 |
| orchestration, spawn_agent | 4 | {'returned': 4} | 0.2740001678466797 | 0 |
| orchestration, wait_agent | 30 | {'returned': 30} | 891.2560000419617 | 0 |
| validation, exec | 17 | {'returned': 17} | 55.150999546051025 | 0 |
| validation, send_message | 3 | {'returned': 3} | 0.18700003623962402 | 0 |

Attribution omissions: 0 events; 6 diagnostics.

## Native lineage

- codex:01a1bde7-e9fa-7351-a75a-a7326e6ff8c8 → codex:01a1bde9-516c-77b2-8ace-d113970d06c7 (spawn)
- codex:01a1bde7-e9fa-7351-a75a-a7326e6ff8c8 → codex:01a1bdf1-0425-7c72-b4ec-f7b2dca79eb7 (spawn)
- codex:01a1bde7-e9fa-7351-a75a-a7326e6ff8c8 → codex:01a1bdf4-ccc1-75a3-a732-2fefda66d3ee (spawn)
- codex:01a1bde7-e9fa-7351-a75a-a7326e6ff8c8 → codex:01a1bdf6-7034-7630-99b3-18999222de2b (spawn)

## Coverage diagnostics

- aggregate_snapshot_excluded: 6

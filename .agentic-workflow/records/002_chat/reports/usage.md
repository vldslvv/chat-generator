# Selected implementation usage

Null means unavailable. Known subtotals exclude missing measurements. Scope and omissions are in usage.json.

| Metric | Total | Known subtotal | Measured records | Missing records |
|---|---:|---:|---:|---:|
| input_tokens | unavailable | 19447830 | 279 | 0 |
| cached_input_tokens | unavailable | 18876416 | 279 | 0 |
| cache_write_input_tokens | unavailable | 0 | 279 | 0 |
| uncached_input_tokens | unavailable | 571414 | 279 | 0 |
| output_tokens | unavailable | 124445 | 279 | 0 |
| reasoning_output_tokens | unavailable | 37210 | 279 | 0 |
| total_tokens | unavailable | 19572275 | 279 | 0 |

## By task

| Group | Total tokens | Known subtotal | Missing records | Tools |
| --- | --- | --- | --- | --- |
| 01_api | unavailable | 1474089 | 0 | 28 |
| 02_python_client | unavailable | 2459214 | 0 | 36 |
| 03_rust_client | unavailable | 2045439 | 0 | 30 |
| orchestration | unavailable | 11386911 | 0 | 116 |
| validation | unavailable | 2206622 | 0 | 39 |

Attribution omissions: 0 events; 3 diagnostics.

## By agent_run

| Group | Total tokens | Known subtotal | Missing records | Tools |
| --- | --- | --- | --- | --- |
| codex:01a1be1d-e869-79c2-851b-b8db0a0441a6 | unavailable | 11386911 | 0 | 116 |
| codex:01a1be1f-32a5-74d3-bf9d-5a5d8db05369 | unavailable | 1474089 | 0 | 28 |
| codex:01a1be22-f90e-7aa3-b6fc-6bb1e8360e81 | unavailable | 2459214 | 0 | 36 |
| codex:01a1be23-3112-7451-84ff-32d4b9425a00 | unavailable | 2045439 | 0 | 30 |
| codex:01a1be2a-4530-76b0-a008-0aefc144c3d1 | unavailable | 1224889 | 0 | 21 |
| codex:01a1be34-27fc-7332-bcb6-836469e9c9b2 | unavailable | 981733 | 0 | 18 |

Attribution omissions: 0 events; 3 diagnostics.

## By role

| Group | Total tokens | Known subtotal | Missing records | Tools |
| --- | --- | --- | --- | --- |
| implementer | unavailable | 5978742 | 0 | 94 |
| supervisor | unavailable | 11386911 | 0 | 116 |
| validator | unavailable | 2206622 | 0 | 39 |

Attribution omissions: 0 events; 3 diagnostics.

## By model

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| gpt-6.1-sol | unavailable | 19572275 | 0 |

Attribution omissions: 0 events; 12 diagnostics.

## By effort

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| high | unavailable | 8185364 | 0 |
| medium | unavailable | 11386911 | 0 |

Attribution omissions: 0 events; 12 diagnostics.

## By model_effort

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| gpt-6.1-sol, high | unavailable | 8185364 | 0 |
| gpt-6.1-sol, medium | unavailable | 11386911 | 0 |

Attribution omissions: 0 events; 12 diagnostics.

## By task_model_effort

| Group | Total tokens | Known subtotal | Missing records |
| --- | --- | --- | --- |
| 01_api, gpt-6.1-sol, high | unavailable | 1474089 | 0 |
| 02_python_client, gpt-6.1-sol, high | unavailable | 2459214 | 0 |
| 03_rust_client, gpt-6.1-sol, high | unavailable | 2045439 | 0 |
| orchestration, gpt-6.1-sol, medium | unavailable | 11386911 | 0 |
| validation, gpt-6.1-sol, high | unavailable | 2206622 | 0 |

Attribution omissions: 0 events; 12 diagnostics.

## By tool

| Group | Observed calls | Outcomes | Observed seconds | Untimed |
| --- | --- | --- | --- | --- |
| exec | 171 | {'returned': 171} | 184.0270004272461 | 0 |
| followup_task | 3 | {'returned': 3} | 0.10299968719482422 | 0 |
| send_message | 46 | {'returned': 46} | 2.730998992919922 | 0 |
| spawn_agent | 5 | {'returned': 5} | 0.15600037574768066 | 0 |
| wait_agent | 24 | {'returned': 24} | 547.029000043869 | 0 |

Attribution omissions: 0 events; 12 diagnostics.

## By task_tool

| Group | Observed calls | Outcomes | Observed seconds | Untimed |
| --- | --- | --- | --- | --- |
| 01_api, exec | 23 | {'returned': 23} | 29.822001457214355 | 0 |
| 01_api, send_message | 5 | {'returned': 5} | 0.2239997386932373 | 0 |
| 02_python_client, exec | 27 | {'returned': 27} | 27.705999612808228 | 0 |
| 02_python_client, send_message | 9 | {'returned': 9} | 0.440000057220459 | 0 |
| 03_rust_client, exec | 23 | {'returned': 23} | 20.09600019454956 | 0 |
| 03_rust_client, send_message | 7 | {'returned': 7} | 0.2239995002746582 | 0 |
| orchestration, exec | 62 | {'returned': 62} | 58.21699905395508 | 0 |
| orchestration, followup_task | 3 | {'returned': 3} | 0.10299968719482422 | 0 |
| orchestration, send_message | 22 | {'returned': 22} | 1.7289998531341553 | 0 |
| orchestration, spawn_agent | 5 | {'returned': 5} | 0.15600037574768066 | 0 |
| orchestration, wait_agent | 24 | {'returned': 24} | 547.029000043869 | 0 |
| validation, exec | 36 | {'returned': 36} | 48.18600010871887 | 0 |
| validation, send_message | 3 | {'returned': 3} | 0.11399984359741211 | 0 |

Attribution omissions: 0 events; 12 diagnostics.

## Native lineage

- codex:01a1be1d-e869-79c2-851b-b8db0a0441a6 → codex:01a1be1f-32a5-74d3-bf9d-5a5d8db05369 (spawn)
- codex:01a1be1d-e869-79c2-851b-b8db0a0441a6 → codex:01a1be22-f90e-7aa3-b6fc-6bb1e8360e81 (spawn)
- codex:01a1be1d-e869-79c2-851b-b8db0a0441a6 → codex:01a1be23-3112-7451-84ff-32d4b9425a00 (spawn)
- codex:01a1be1d-e869-79c2-851b-b8db0a0441a6 → codex:01a1be2a-4530-76b0-a008-0aefc144c3d1 (spawn)
- codex:01a1be1d-e869-79c2-851b-b8db0a0441a6 → codex:01a1be34-27fc-7332-bcb6-836469e9c9b2 (spawn)

## Coverage diagnostics

- aggregate_snapshot_excluded: 9
- ambiguous_dispatch_turn: 3

# Logs Simulator

Production-like Python CLI project for generating realistic log datasets for parser/normalization/storage pipelines and Grafana/Loki-style analysis.

It generates multiple raw log formats from one canonical event model and writes a parallel `ground_truth.jsonl` file for validation.

## Features

- Python 3.11+ CLI with YAML config
- Canonical event model as single source of truth
- Required formats:
  - NDJSON (`.jsonl`)
  - CSV (`.csv`)
  - Plain app logs (`.log`)
  - logfmt (`.logfmt`)
  - Simplified RFC5424-like syslog (`.syslog`)
  - Web access logs (combined style)
  - Multiline stack traces (Python / Java / Node.js)
  - Mixed format in one file (`mixed`)
- Noise and realism:
  - Baseline traffic + spikes
  - Time-based incidents with elevated errors/latency
  - Correlation latency -> 5xx
  - Duplicates
  - Out-of-order timestamps
  - Missing fields
  - Malformed lines
  - Variable time zones for text logs
- File rotation by size and time
- Date/service/format directory layout
- `ground_truth.jsonl` with `event_id` linkage
- `--challenge-mode` for harder parser scenarios

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Quick Start

Validate config:

```bash
python -m logs_simulator.cli validate-config --config config.example.yaml
```

Generate dataset:

```bash
python -m logs_simulator.cli generate \
  --config config.example.yaml \
  --out-dir ./logs_out \
  --duration-sec 600 \
  --events-per-sec 200 \
  --seed 42
```

Stream mode (Ctrl+C to stop):

```bash
python -m logs_simulator.cli stream \
  --config config.example.yaml \
  --out-dir ./logs_out \
  --events-per-sec 200 \
  --seed 42
```

Challenge mode + gzip:

```bash
python -m logs_simulator.cli generate \
  --config config.example.yaml \
  --out-dir ./logs_out \
  --duration-sec 300 \
  --events-per-sec 250 \
  --seed 42 \
  --challenge-mode \
  --gzip
```

## Output Layout

```text
logs_out/YYYY/MM/DD/{service}/{format}/...
logs_out/YYYY/MM/DD/ground_truth/ground_truth.jsonl
```

Example path:

```text
logs_out/2026/02/12/auth/jsonl/auth_jsonl_20260212T100001Z_0000.jsonl
```

## Canonical Event Schema

Every generated raw event originates from canonical fields:

- `event_id` (uuid)
- `ts` (RFC3339 UTC)
- `level`
- `service`
- `env`
- `host`
- `region`
- `message`
- `request_id`, `trace_id`, `span_id`
- `user_id` (optional)
- `http_method`, `path`, `status_code` (optional)
- `latency_ms` (optional)
- `error_code`, `exception_type` (optional)
- `tags` (dict/list)
- `raw_payload` (optional)

## Example Log Lines by Format

NDJSON / JSONL:

```json
{"event_id":"4d7bb1dc-f99d-43af-b02e-a2f17d65f13d","ts":"2026-02-12T10:15:30.123Z","level":"INFO","service":"auth","message":"request completed method=POST path=/auth/login status=200 latency_ms=53","request_id":"req_ea491b46cbdd","trace_id":"e5d5e8f0f56f9d5f8405f0c7e5f1e653","span_id":"b9ddf8f8b09f2c66"}
```

CSV:

```csv
event_id,ts,level,service,env,host,region,message,request_id,trace_id,span_id,user_id,http_method,path,status_code,latency_ms,error_code,exception_type,tags,raw_payload
4d7bb1dc-f99d-43af-b02e-a2f17d65f13d,2026-02-12T10:15:30.123Z,INFO,auth,prod,auth-03.node.local,us-east-1,request completed method=POST path=/auth/login status=200 latency_ms=53,req_ea491b46cbdd,e5d5e8f0f56f9d5f8405f0c7e5f1e653,b9ddf8f8b09f2c66,usr_182321,POST,/auth/login,200,53,,,,"{\"team\":\"identity\"}",
```

Plain text app log:

```text
2026-02-12T10:15:30.123Z INFO auth event_id=4d7bb1dc-f99d-43af-b02e-a2f17d65f13d request_id=req_ea491b46cbdd trace_id=e5d5e8f0f56f9d5f8405f0c7e5f1e653 span_id=b9ddf8f8b09f2c66 env=prod region=us-east-1 method=POST path=/auth/login status=200 latency_ms=53 message="request completed method=POST path=/auth/login status=200 latency_ms=53"
```

logfmt:

```text
ts=2026-02-12T10:15:30.123Z level=INFO service=auth event_id=4d7bb1dc-f99d-43af-b02e-a2f17d65f13d request_id=req_ea491b46cbdd trace_id=e5d5e8f0f56f9d5f8405f0c7e5f1e653 span_id=b9ddf8f8b09f2c66 env=prod host=auth-03.node.local region=us-east-1 method=POST path=/auth/login status=200 latency_ms=53 message="request completed method=POST path=/auth/login status=200 latency_ms=53"
```

Syslog-like:

```text
<166>1 2026-02-12T10:15:30.123Z auth-03.node.local auth - 4d7bb1dc-f99d-43af-b02e-a2f17d65f13d [meta request_id="req_ea491b46cbdd" trace_id="e5d5e8f0f56f9d5f8405f0c7e5f1e653" span_id="b9ddf8f8b09f2c66" env="prod" region="us-east-1" status="200" latency_ms="53"] request completed method=POST path=/auth/login status=200 latency_ms=53
```

Access log (combined style):

```text
auth-03.node.local - usr_182321 [12/Feb/2026:10:15:30 +0000] "POST /auth/login HTTP/1.1" 200 2048 "https://grafana.local/d/ops" "Mozilla/5.0" event_id=4d7bb1dc-f99d-43af-b02e-a2f17d65f13d trace_id=e5d5e8f0f56f9d5f8405f0c7e5f1e653 service=auth env=prod latency_ms=53
```

Multiline (Python / Java / Node style examples are generated):

```text
2026-02-12T10:16:02.334Z ERROR auth event_id=cbf13344-386a-4f57-80e8-8bca289cb8b0 request_id=req_8dca93822d4a trace_id=785ae7cdd39f29f0d3fdb0b95a3b57c9 Traceback (most recent call last):
  File "/srv/auth/module_0.py", line 224, in handle
    handle(request_0)
  File "/srv/auth/module_1.py", line 315, in process
    process(request_1)
...
TimeoutError: request failed service=auth method=POST path=/auth/login status=503 latency_ms=2200 code=UPSTREAM_502 [error_code=UPSTREAM_502]
The above exception was the direct cause of the following exception:
PipelineException: failed to persist event
```

Mixed format (same file contains JSON + plain + logfmt lines):

```text
{"event_id":"...","ts":"2026-02-12T10:17:00.004Z","level":"INFO","service":"api-gateway",...}
2026-02-12T10:17:00.106Z WARN api-gateway event_id=... request_id=... message="request completed with warning ..."
ts=2026-02-12T10:17:00.205Z level=ERROR service=api-gateway event_id=... message="request failed ..."
```

## Parser Testing Guide

Use `ground_truth.jsonl` for exact matching by `event_id`:

1. Parse raw logs by format.
2. Normalize parsed output into canonical-like fields.
3. Join parser output with `ground_truth.jsonl` on `event_id`.
4. Measure precision/recall and field-level correctness.
5. Run again with `--challenge-mode` to stress robustness.

## Built-in Edge Cases

- Duplicated events (same `event_id`)
- Out-of-order timestamps
- Missing optional fields in raw output
- Malformed lines for parser failure paths
- Mixed timezone offsets in text logs
- Long stack traces (10-30 lines)
- `Caused by`, nested exceptions, truncated stack traces
- Mixed-format files

## Tests

```bash
pytest
```

Covered scenarios:

- Seed-based deterministic output
- Presence of all required formats
- Multiline correctness and stack-trace-like content
- Presence of `event_id` in raw logs
- Ground-truth consistency with raw logs (with malformed tolerance)

## Convenience Targets

```bash
make validate
make run
make stream
make sample
make test
```

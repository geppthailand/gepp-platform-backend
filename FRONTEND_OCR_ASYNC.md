# Frontend task: switch OCR to the async job API

## Why

The OCR endpoint reads uploaded documents with a vision model. That takes
**20–45 seconds**. API Gateway cuts any request off at **30 seconds** and this
limit cannot be raised, so the current synchronous call returns **503** on
anything but a small upload — even though the work actually succeeded on the
server.

The backend now exposes the same OCR as a job you start and then poll.

## What changes

One request becomes two: start the job, then poll until it finishes.

**Nothing about the result changes.** The object you get back at the end is
byte-identical to what the current endpoint returns today, so the code that
fills the form stays exactly as it is. Only the waiting changes.

## Two flows, two URLs

There are two OCR endpoints today and there are two job endpoints, one for
each. They behave identically — only the path differs, and the path is what
selects the reader.

| page | old (synchronous) | new (job) |
|---|---|---|
| transactions | `POST /api/epr/ai_audit/ocr` | `POST /api/epr/ai_audit/ocr/jobs` |
| recycler audit | `POST /api/epr/ai_audit/recycler-audit-ocr` | `POST /api/epr/ai_audit/recycler-audit-ocr/jobs` |

Poll the job on the URL family you posted to:

```
GET /api/epr/ai_audit/ocr/jobs/{job_id}
GET /api/epr/ai_audit/recycler-audit-ocr/jobs/{job_id}
```

Either poll path will in fact resolve any job id, but matching the pair keeps
each page's code symmetrical.

The `fields` shape stays what each page already sends: transactions send the
nested `record_field` form, the recycler audit sends the flat list with
`section` on each field. Sending one page's shape to the other page's URL
fails the job.

## The old calls (stop using)

```
POST /api/epr/ai_audit/ocr
POST /api/epr/ai_audit/recycler-audit-ocr
{ "files": [...], "fields": [...] }

→ 200 { "success": true, "data": { ...result... } }
```

Keep it working in your code until you have switched over; it will be removed
after. It still 503s on larger uploads, which is the bug being fixed.

## The new calls

### 1. Start the job

```
POST /api/epr/ai_audit/ocr/jobs                  ← transactions
POST /api/epr/ai_audit/recycler-audit-ocr/jobs   ← recycler audit
Content-Type: application/json

{ "files": [...], "fields": [...] }     ← EXACTLY the same body as before
```

Returns immediately, well under a second:

```json
{
  "success": true,
  "data": {
    "success": true,
    "data": { "job_id": "ocr_3f9a2c7d8e1b4a60", "status": "pending" }
  }
}
```

**Note the double `data`.** That is not a typo — this API already nests the
response that way today, and these endpoints match it so your existing
unwrapping helper keeps working. Unwrap it the same way you unwrap the current
OCR response.

### 2. Poll for the result

```
GET /api/epr/ai_audit/ocr/jobs/{job_id}
```

```json
{
  "success": true,
  "data": {
    "success": true,
    "data": {
      "job_id": "ocr_3f9a2c7d8e1b4a60",
      "kind": "transaction",
      "status": "pending" | "processing" | "done" | "failed",
      "result": { ...same shape as today's response... },
      "error": "human readable message"
    }
  }
}
```

- `result` is `null` until `status` is `"done"`.
- `error` is `null` unless `status` is `"failed"`.
- A `job_id` that does not exist returns **404**.

## What to implement

1. On submit, call **POST** on the job URL for that page (see the table above)
   and keep the `job_id`.
2. Poll **GET** `<same URL family>/jobs/{job_id}` **every 2 seconds**.
3. Stop polling when `status` is `done` or `failed`.
4. On `done`: take the job's `result` and fill the form exactly as the current
   code does with the old response body. This part should be unchanged logic.
5. On `failed`: show the job's `error` and let the user retry.
6. **Give up after 2 minutes** (60 polls) and show a timeout message. Do not
   poll forever.
7. Show a spinner for `pending` and `processing`. Typical finish is 20–45
   seconds, so a plain spinner is not enough — see below.

## UI requirements

- The wait is long enough that users will think the app has frozen. Show
  elapsed time or a progress message, not just a spinner.
- Disable the submit button while a job is in flight so the same upload is not
  queued twice.
- Let the user cancel: stop polling and drop the `job_id`. There is no cancel
  endpoint, the job simply finishes unread, and that is fine.
- If the user navigates away and comes back, you may keep the `job_id` and
  resume polling. Results are retained, so this works.

## Error handling

| what happened | how you see it | what to do |
|---|---|---|
| bad request (no files) | POST returns 400 | show the message, do not poll |
| job not found / expired | GET returns 404 | show "expired, please retry" |
| OCR failed | `status: "failed"` | show the job's `error`, offer retry |
| still working | `status: "pending"` / `"processing"` | keep polling |
| took too long | your own 2 minute cap | show timeout, offer retry |

Poll failures (network blips, a 5xx on the GET) should not kill the job. Retry
the next poll; only give up at the 2 minute cap.

## Do not

- Do not poll faster than every 2 seconds. It adds load and does not make the
  model finish sooner.
- Do not change how `files` or `fields` are built. The request body is
  unchanged.
- Do not change the form-filling code. The `result` object is the same.
- Do not assume the job finishes on the first poll. It will not.

## Test checklist

- [ ] Transactions page: small upload (2–3 files) fills the form correctly
- [ ] Recycler audit page: still works, now via its own job URL
- [ ] Large upload (6–8 files) — this is the case that used to 503 — completes
- [ ] Spinner shows the whole time and clears on completion
- [ ] Submit is disabled while a job is running
- [ ] Cancel stops the polling
- [ ] A failed job shows its message and can be retried
- [ ] Timeout fires and is recoverable if the job never finishes

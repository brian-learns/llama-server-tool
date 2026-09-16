"""
### GET `/metrics`: Prometheus compatible metrics exporter

This endpoint is only accessible if `--metrics` is set.

In *router mode* the query param `?model={model_id}` has to be set. This endpoint will respond with status code 400 `model name is missing from the request` if not set.

#### Available metrics

| Metric | Type | Description |
| ------ | ---------------------- | ----------- |
| `llamacpp:prompt_tokens_total` | Counter | Number of prompt tokens processed. |
| `llamacpp:prompt_seconds_total` | Counter | Prompt process time in seconds. |
| `llamacpp:prompt_tokens_seconds` | Gauge | Average prompt throughput in tokens/s. |
| `llamacpp:tokens_predicted_total` | Counter | Number of generation tokens processed. |
| `llamacpp:tokens_predicted_seconds_total` | Counter | Predict process time in seconds. |
| `llamacpp:predicted_tokens_seconds` | Gauge | Average generation throughput in tokens/s. |
| `llamacpp:requests_processing` | Gauge | Number of requests processing. |
| `llamacpp:requests_deferred` | Gauge | Number of requests deferred. |
| `llamacpp:n_tokens_max` | Counter | High watermark of the context size observed. |
| `llamacpp:n_decode_total` | Counter | Total Number of llama_decode() calls. |
| `llamacpp:n_busy_slots_per_decode` | Gauge | Average number of busy slots per llama_decode() call. |
| `llamacpp:spec_decode_num_draft_tokens_total` | Counter | Total draft tokens generated (0 when spec-decode is off). |
| `llamacpp:spec_decode_num_accepted_tokens_total` | Counter | Total draft tokens accepted by the target model (0 when spec-decode is off). |
| `llamacpp:spec_decode_num_drafts_total` | Counter | Total speculative decoding verification steps (0 when spec-decode is off). |
| `llamacpp:spec_decode_num_accepted_tokens_per_pos_total` | Counter | Accepted tokens per draft position (labeled `position="N"`; absent when spec-decode is off or before the first completed speculative request). |

"""

async function request(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      if (payload.detail) detail = payload.detail
    } catch {
      // non-JSON error body — keep the status line
    }
    throw new Error(detail)
  }
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  patch: (path, body) => request('PATCH', path, body),
  put: (path, body) => request('PUT', path, body),

  streamRun(runId, onEvent) {
    const source = new EventSource(`/api/runs/${runId}/events`)
    source.onmessage = (message) => {
      const event = JSON.parse(message.data)
      onEvent(event)
      if (event.type === 'done') source.close()
    }
    source.onerror = () => source.close()
    return () => source.close()
  },
}

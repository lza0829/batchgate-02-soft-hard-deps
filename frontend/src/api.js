export async function getJSON(url) {
  const r = await fetch(url)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function postJSON(url, body = {}) {
  return sendJSON('POST', url, body)
}

export async function patchJSON(url, body) {
  return sendJSON('PATCH', url, body)
}

export async function putJSON(url, body) {
  return sendJSON('PUT', url, body)
}

async function sendJSON(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    let message = await r.text()
    try {
      const parsed = JSON.parse(message)
      message = parsed.detail || message
    } catch { /* keep raw text */ }
    throw new Error(message)
  }
  return r.json()
}
